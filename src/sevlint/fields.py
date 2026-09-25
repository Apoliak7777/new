"""Fields and models that exist in other Odoo versions but not in the target one.

The index (tools/fields_index.py) holds, per Community model, the fields each version has.
Only names the index knows from *some* version are judged: a field or model that Odoo had
in another version and dropped (or renamed) in the target is a near-certain error, while
unknown names may come from Enterprise or custom modules and are left alone.
"""
from __future__ import annotations

import ast
import difflib
import functools
import gzip
import json
from importlib import resources

from .engine import Diagnostic, RUNTIME
from .profile import normalize_version

RECORDSET_METHODS = {"sudo", "with_context", "with_user", "with_company", "with_env", "browse", "search",
                     "filtered", "filtered_domain", "sorted", "exists", "create", "copy", "new", "grouped"}
VALS_METHODS = {"write": 0, "create": 0, "update": 0, "new": 0}
DOMAIN_METHODS = {"search", "search_count", "search_read", "search_fetch", "filtered_domain", "read_group",
                  "_read_group", "formatted_read_group", "web_search_read"}
NAMES_METHODS = {"mapped", "filtered", "sorted", "read"}  # string or list of field (paths)
DOMAIN_OPERATORS = {"&", "|", "!"}


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


def _uses(tree: ast.Module, types: _Types):
    """(model, field, line) for every statically attributable field use, and (model, line)
    for every env['model'] access."""
    fields, models = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _is_env(node.value) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            models.append((node.slice.value, node.lineno))
        if isinstance(node, ast.Attribute) and not isinstance(node.ctx, ast.Del):
            model = types.model_of(node.value)
            if model:
                fields.append((model, node.attr, node.lineno))
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str) and not _is_env(node.value):
            model = types.model_of(node.value)
            if model:
                fields.append((model, node.slice.value, node.lineno))
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
                        names += [(k.value, k.lineno) for k in d.keys if isinstance(k, ast.Constant)
                                  and isinstance(k.value, str)]
            if method in DOMAIN_METHODS:
                names += _domain_fields(_arg(node, 0, "domain"))
            if method == "search_read" or method == "search_fetch":
                names += _strings(_arg(node, 1, "fields" if method == "search_read" else "field_names"))
            if method in NAMES_METHODS:
                names += _strings(_arg(node, 0, "fields" if method == "read" else "func"))
            fields += [(model, name.split(".", 1)[0], line) for name, line in names]
    return fields, models


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
    for model, field, line in uses:
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
