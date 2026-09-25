#!/usr/bin/env python3
"""Build sevlint's field index: which fields each Odoo Community model has, per version.

Only the AST of the model sources is read (Odoo is never imported). For every class with
``_name``/``_inherit`` the class-level ``x = fields.Char(...)`` declarations are collected;
fields are then resolved through ``_inherit`` (mixins such as mail.thread) and ``_inherits``
(delegation, e.g. res.users -> res.partner). The result for all versions is stored in
``src/sevlint/data/fields.json.gz`` as ``{model: {field: bitmask over versions}}``.

Usage (after the branches exist as sparse clones, see sync_odoo.py)::

    python tools/fields_index.py --src-root /tmp/odoo-src 17.0 saas-17.1 ... 20.0
"""
from __future__ import annotations

import argparse
import ast
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_odoo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "sevlint" / "data" / "fields.json.gz"
MODEL_PATTERNS = [
    "/addons/*/models.py",
    "/addons/*/models/",
    "/addons/*/wizard/",
    "/addons/*/wizards/",
    "/addons/*/report/",
    "/odoo/addons/base/models/",
    "/odoo/addons/base/wizard/",
]
FIELD_CLASSES = {
    "Id", "Boolean", "Integer", "Float", "Monetary", "Char", "Text", "Html", "Date", "Datetime", "Binary",
    "Image", "Selection", "Reference", "Many2one", "One2many", "Many2many", "Many2oneReference", "Json",
    "Properties", "PropertiesDefinition",
}
MAGIC_FIELDS = {"id", "display_name", "create_uid", "create_date", "write_uid", "write_date"}


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def _is_field_call(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "fields":
        return func.attr in FIELD_CLASSES
    return isinstance(func, ast.Name) and func.id in FIELD_CLASSES


def parse_models(source: str) -> list[tuple[str, set[str], set[str], set[str]]]:
    """(model, own fields, parents via _inherit, delegated models via _inherits) per class."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        attrs: dict[str, object] = {}
        fields: set[str] = set()
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign):
                targets, value = stmt.targets, stmt.value
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                targets, value = [stmt.target], stmt.value
            else:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id in ("_name", "_inherit", "_inherits"):
                    attrs[target.id] = _literal(value)
                elif _is_field_call(value):
                    fields.add(target.id)
        name, inherit = attrs.get("_name"), attrs.get("_inherit")
        parents = {inherit} if isinstance(inherit, str) else set(inherit or []) if isinstance(inherit, list) else set()
        if not isinstance(name, str):
            if isinstance(inherit, str):
                name = inherit
            elif isinstance(inherit, list) and inherit and isinstance(inherit[0], str):
                name = inherit[0]
            else:
                continue  # not a model class (or a computed name)
        delegates = set(attrs["_inherits"]) if isinstance(attrs.get("_inherits"), dict) else set()
        out.append((name, fields, {p for p in parents if isinstance(p, str)} - {name}, delegates))
    return out


def collect(src: Path) -> dict[str, dict[str, set[str]]]:
    models: dict[str, dict[str, set[str]]] = {}
    files = list((src / "addons").glob("*/models.py"))
    for sub in ("models", "wizard", "wizards", "report"):
        files += (src / "addons").glob(f"*/{sub}/**/*.py")
    files += (src / "odoo" / "addons" / "base").glob("models/**/*.py")
    files += (src / "odoo" / "addons" / "base").glob("wizard/**/*.py")
    for path in files:
        for name, fields, parents, delegates in parse_models(path.read_text(encoding="utf-8", errors="replace")):
            entry = models.setdefault(name, {"fields": set(), "parents": set(), "delegates": set()})
            entry["fields"] |= fields
            entry["parents"] |= parents
            entry["delegates"] |= delegates
    return models


def resolve(models: dict[str, dict[str, set[str]]]) -> dict[str, set[str]]:
    resolved: dict[str, set[str]] = {}

    def fields_of(name: str, stack: tuple[str, ...] = ()) -> set[str]:
        if name in resolved:
            return resolved[name]
        if name in stack or name not in models:
            return set()
        entry = models[name]
        out = set(entry["fields"]) | MAGIC_FIELDS
        for parent in entry["parents"] | entry["delegates"]:
            out |= fields_of(parent, stack + (name,))
        resolved[name] = out
        return out

    for name in models:
        fields_of(name)
    return resolved


def build(branches: list[str], src_root: Path) -> dict:
    per_version: dict[str, dict[str, set[str]]] = {}
    for branch in branches:
        src = sync_odoo.checkout(branch, src_root)
        sparse = src / ".git" / "info" / "sparse-checkout"
        existing = sparse.read_text().splitlines()
        missing = [p for p in MODEL_PATTERNS if p not in existing]
        if missing:
            sync_odoo._run("git", "-C", str(src), "sparse-checkout", "add", *missing)
        per_version[branch] = resolve(collect(src))
        print(f"{branch}: {len(per_version[branch])} models", file=sys.stderr)
    index: dict[str, dict[str, int]] = {}
    for bit, branch in enumerate(branches):
        for model, fields in per_version[branch].items():
            model_index = index.setdefault(model, {})
            for field in fields:
                model_index[field] = model_index.get(field, 0) | (1 << bit)
    return {"versions": branches, "models": {m: dict(sorted(f.items())) for m, f in sorted(index.items())}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("branches", nargs="+")
    parser.add_argument("--src-root", type=Path, required=True)
    args = parser.parse_args(argv)
    for branch in args.branches:
        if not sync_odoo.BRANCH_RE.fullmatch(branch):
            parser.error(f"not an Odoo release branch: {branch!r}")
    data = build(args.branches, args.src_root)
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    OUT.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    print(f"{OUT.relative_to(ROOT)}: {len(data['models'])} models, {len(raw) // 1024} KiB json, "
          f"{OUT.stat().st_size // 1024} KiB gz", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
