"""Fields and models that exist in other Odoo versions but not in the target one.

The index (tools/fields_index.py) holds, per Community model, the fields each version has.
Only names the index knows from *some* version are judged: a field or model that Odoo had
in another version and dropped (or renamed) in the target is a near-certain error, while
unknown names may come from Enterprise or custom modules and are left alone.

With a live database (``sevlint remote``) the database's own ir.model / ir.model.fields are
the reference instead: every field and model name is judged, Studio ``x_`` fields included.
"""
from __future__ import annotations

import ast
import difflib
import functools
import gzip
import json
from dataclasses import dataclass, field as dc_field
from importlib import resources

from .engine import Diagnostic, RUNTIME
from .profile import normalize_version

RECORDSET_METHODS = {"sudo", "with_context", "with_user", "with_company", "with_env", "browse", "search",
                     "filtered", "filtered_domain", "sorted", "exists", "create", "copy", "new", "grouped"}
VALS_METHODS = {"write": 0, "create": 0, "update": 0, "new": 0}
DOMAIN_METHODS = {"search", "search_count", "search_read", "search_fetch", "filtered_domain", "read_group",
                  "_read_group", "formatted_read_group", "web_search_read"}
NAMES_METHODS = {"mapped": "func", "filtered": "func", "sorted": "key", "read": "fields"}  # field (path) strings
DOMAIN_OPERATORS = {"&", "|", "!"}
MAGIC_FIELDS = frozenset({"id", "display_name", "create_uid", "create_date", "write_uid", "write_date"})
# How a name is used: `rec.name` (could be a method), a vals key of write()/create() (an override may
# consume extra keys), or where only a field is valid (domains, rec['name'], mapped('name'), ...).
ATTR, VALS, FIELD = "attr", "vals", "field"


@functools.lru_cache(maxsize=1)
def _index() -> tuple[list[str], dict[str, dict[str, int]]]:
    raw = resources.files("sevlint.data").joinpath("fields.json.gz").read_bytes()
    data = json.loads(gzip.decompress(raw))
    return data["versions"], data["models"]


def _bit(version: str) -> int | None:
    versions, _ = _index()
    version = normalize_version(version)
    return 1 << versions.index(version) if version in versions else None


def _span(mask: int) -> str:
    """'17.0–saas-18.1' style ranges of the versions in ``mask``."""
    versions, _ = _index()
    present = [i for i in range(len(versions)) if mask >> i & 1]
    runs, start = [], None
    for pos, i in enumerate(present):
        if start is None:
            start = i
        if pos + 1 == len(present) or present[pos + 1] != i + 1:
            runs.append(versions[start] if start == i else f"{versions[start]}–{versions[i]}")
            start = None
    return ", ".join(runs)


def model_from_xmlid(ref: str) -> str | None:
    """'base.model_res_users' / 'model_sale_order_line' -> the model it names, if unambiguous."""
    name = ref.rsplit(".", 1)[-1]
    if not name.startswith("model_"):
        return None
    flat = name[len("model_"):]
    _, models = _index()
    matches = [m for m in models if m.replace(".", "_") == flat]
    return matches[0] if len(matches) == 1 else None


class _Types:
    """Which Odoo model a name or expression holds, as far as it is statically obvious."""

    def __init__(self, tree: ast.Module, action_model: str | None):
        self.names: dict[str, str | None] = {"user": "res.users"}
        if action_model:
            self.names.update(record=action_model, records=action_model, model=action_model)
        assigned: dict[str, set[str | None]] = {}
        for _ in range(2):  # a second pass resolves names assigned from other names
            assigned.clear()
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assigned.setdefault(target.id, set()).add(self.model_of(node.value))
                elif isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.target, ast.Name):
                    assigned.setdefault(node.target.id, set()).add(self.model_of(node.iter))
                elif isinstance(node, ast.arg):
                    assigned.setdefault(node.arg, set()).add(None)
            for name, models in assigned.items():
                self.names[name] = models.pop() if len(models) == 1 else None

    def model_of(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str) and _is_env(node.value):
                return node.slice.value
            return self.model_of(node.value)  # records[0], records[1:]
        if isinstance(node, ast.Name):
            return self.names.get(node.id)
        if isinstance(node, ast.Attribute) and _is_env(node.value):
            return {"user": "res.users", "company": "res.company", "companies": "res.company"}.get(node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in RECORDSET_METHODS:
            return self.model_of(node.func.value)
        return None


def _is_env(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "env") or (isinstance(node, ast.Attribute) and node.attr == "env")


def _strings(node: ast.AST | None) -> list[tuple[str, int]]:
    """Constant strings in a string or a list/tuple of strings."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [(node.value, node.lineno)]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [(e.value, e.lineno) for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _domain_fields(node: ast.AST | None) -> list[tuple[str, int]]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    out = []
    for leaf in node.elts:
        if isinstance(leaf, (ast.Tuple, ast.List)) and leaf.elts:
            first = leaf.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value not in DOMAIN_OPERATORS:
                out.append((first.value, first.lineno))
    return out


def _arg(call: ast.Call, position: int, keyword: str) -> ast.AST | None:
    if len(call.args) > position:
        return call.args[position]
    return next((k.value for k in call.keywords if k.arg == keyword), None)


def _field_names(method: str, node: ast.AST | None) -> list[tuple[str, int]]:
    """Field names in a mapped/filtered/read argument or a sorted() order spec ('date desc, id')."""
    names = _strings(node)
    if method == "sorted":
        names = [(part.split()[0], line) for spec, line in names for part in spec.split(",") if part.split()]
    return names


def _uses(tree: ast.Module, types: _Types):
    """(model, field, line, kind) for every statically attributable field use (kind: ATTR, VALS
    or FIELD), and (model, line) for every env['model'] access."""
    fields, models = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _is_env(node.value) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            models.append((node.slice.value, node.lineno))
        if isinstance(node, ast.Attribute) and not isinstance(node.ctx, ast.Del):
            model = types.model_of(node.value)
            if model:
                fields.append((model, node.attr, node.lineno, ATTR))
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str) and not _is_env(node.value):
            model = types.model_of(node.value)
            if model:
                fields.append((model, node.slice.value, node.lineno, FIELD))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            model = types.model_of(node.func.value)
            if not model:
                continue
            names: list[tuple[str, int]] = []
            if method in VALS_METHODS:
                vals = _arg(node, 0, "vals" if method != "create" else "vals_list")
                dicts = vals.elts if isinstance(vals, (ast.List, ast.Tuple)) else [vals]
                for d in dicts:
                    if isinstance(d, ast.Dict):
                        fields += [(model, k.value, k.lineno, VALS) for k in d.keys
                                   if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value]
            if method in DOMAIN_METHODS:
                names += _domain_fields(_arg(node, 0, "domain"))
            if method == "search_read" or method == "search_fetch":
                names += _strings(_arg(node, 1, "fields" if method == "search_read" else "field_names"))
            if method in NAMES_METHODS:
                names += _field_names(method, _arg(node, 0, NAMES_METHODS[method]))
            fields += [(model, name.split(".", 1)[0], line, FIELD) for name, line in names if name]
    return fields, models


def referenced_models(tree: ast.Module, action_model: str | None) -> set[str]:
    """Models whose fields the code uses or that it looks up in env (to fetch their live schema)."""
    uses, model_uses = _uses(tree, _Types(tree, action_model))
    return {model for model, *_ in uses} | {model for model, _ in model_uses} | ({action_model} - {None})


def check_fields(tree: ast.Module, version: str, action_model: str | None) -> list[Diagnostic]:
    bit = _bit(version)
    if bit is None:
        return []
    _, index = _index()
    types = _Types(tree, action_model)
    uses, model_uses = _uses(tree, types)
    out: list[Diagnostic] = []
    for model, line in model_uses:
        known = index.get(model)
        if known is not None and not any(mask & bit for mask in known.values()):
            present = functools.reduce(lambda a, b: a | b, known.values(), 0)
            out.append(Diagnostic(line, "W205", f"model `{model}` is not in Odoo Community "
                                                f"{normalize_version(version)} (it is in {_span(present)}); unless an "
                                                f"Enterprise or custom module provides it: KeyError, {RUNTIME}",
                                  "warning"))
    seen: set[tuple[str, str, int]] = set()
    for model, field, line, _kind in uses:
        known = index.get(model)
        if known is None or field.startswith(("_", "x_")) or (model, field, line) in seen:
            continue
        mask = known.get(field)
        if mask is None or mask & bit:
            continue  # unknown everywhere (custom/Enterprise/method) or present in this version
        seen.add((model, field, line))
        target_fields = [f for f, m in known.items() if m & bit]
        new_fields = [f for f in target_fields if not known[f] & mask]  # appeared when this one vanished
        renamed = difflib.get_close_matches(field, new_fields, n=1, cutoff=0.6)
        where = f"`{model}` in Odoo {normalize_version(version)} (it exists in {_span(mask)})"
        if renamed:  # a similar field replaced it: a rename, e.g. groups_id -> group_ids
            out.append(Diagnostic(line, "E203", f"field `{field}` was renamed: it does not exist on {where}; "
                                                f"use `{renamed[0]}` ({RUNTIME})"))
        else:
            similar = difflib.get_close_matches(field, target_fields, n=1, cutoff=0.75)
            hint = f"; similar: `{similar[0]}`" if similar else ""
            out.append(Diagnostic(line, "W203", f"field `{field}` is not on {where}{hint}; unless an Enterprise or "
                                                f"custom module adds it, this fails at runtime", "warning"))
    return out


@dataclass(frozen=True)
class LiveSchema:
    """What one database has: installed models, and the fields of the models the code uses."""
    models: frozenset[str]
    fields: dict[str, frozenset[str]] = dc_field(default_factory=dict)


def _guarded_models(tree: ast.Module) -> set[str]:
    """Models the code looks up only after checking for them ('x.y' in env) or inside try:."""
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, str) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) \
                and any(_is_env(c) for c in node.comparators):
            guarded.add(node.left.value)
        elif isinstance(node, ast.Try) and node.handlers:
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Subscript) and _is_env(sub.value) and isinstance(sub.slice, ast.Constant) \
                            and isinstance(sub.slice.value, str):
                        guarded.add(sub.slice.value)
    return guarded


def check_live_fields(tree: ast.Module, version: str, action_model: str | None,
                      schema: LiveSchema) -> list[Diagnostic]:
    """E204/W204/E205 against the live database: exact, Enterprise/custom/Studio fields included.

    ``rec.name`` is judged only when ``name`` is a field in some Odoo version or an ``x_`` name
    (otherwise it may be a method); an unknown vals key of write()/create() is a warning (the
    model's override may consume it); names in domains, rec['name'] and mapped()/filtered()/
    sorted()/read() must be fields."""
    _, index = _index()
    types = _Types(tree, action_model)
    uses, model_uses = _uses(tree, types)
    out: list[Diagnostic] = []
    guarded = _guarded_models(tree)
    for model, line in model_uses:
        if model not in schema.models and model not in guarded:
            out.append(Diagnostic(line, "E205", f"model `{model}` is not installed in this database "
                                                f"(KeyError, {RUNTIME})"))
    seen: set[tuple[str, str, int]] = set()
    for model, field, line, kind in uses:
        live = schema.fields.get(model)
        if live is None or field in live or field in MAGIC_FIELDS or (model, field, line) in seen:
            continue
        known = index.get(model, {})
        evidence = field in known or field.startswith("x_")  # a field name in some Odoo version, or custom
        if kind == ATTR and not evidence:
            continue  # possibly a method
        seen.add((model, field, line))
        mask = known.get(field)
        bit = _bit(version)
        renamed = []
        if mask and bit is not None:
            new_fields = [f for f, m in known.items() if m & bit and not m & mask and f in live]
            renamed = difflib.get_close_matches(field, new_fields, n=1, cutoff=0.6)
        similar = renamed or difflib.get_close_matches(field, sorted(live), n=1, cutoff=0.75)
        hint = f"; renamed, use `{renamed[0]}`" if renamed else f"; similar: `{similar[0]}`" if similar else ""
        if kind == VALS and not evidence:
            out.append(Diagnostic(line, "W204", f"`{field}` is not a field of `{model}` in this database{hint}; "
                                                f"unless the model's create()/write() consumes this key: ValueError "
                                                f"(Invalid field), {RUNTIME}", "warning"))
            continue
        error = {ATTR: "AttributeError", VALS: "ValueError"}.get(kind, "ValueError/KeyError")
        out.append(Diagnostic(line, "E204", f"field `{field}` does not exist on `{model}` in this database"
                                            f"{hint} ({error}, {RUNTIME})"))
    return out
