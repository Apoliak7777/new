#!/usr/bin/env python3
"""Regenerate sevlint's per-version data from Odoo's own source.

For every Odoo branch given on the command line this script:

* sparse-clones the few files it needs from github.com/odoo/odoo (or reuses
  ``--src-root/src-<branch>`` if it already exists),
* extracts the opcode name lists, ``_UNSAFE_ATTRIBUTES``, ``_BUILTINS`` and the
  wrapped-module whitelists from ``odoo/tools/safe_eval.py`` by walking its AST
  (the file is never imported or executed),
* extracts the names every ``_get_eval_context`` override adds for
  ``ir.actions.server`` (core and per addon),
* writes ``src/sevlint/data/odoo-<branch>.json`` and copies ``safe_eval.py`` to
  ``tests/fixtures/odoo/<branch>/`` where the oracle test uses it.

Any construct the extractor does not recognise aborts the run: a silent
partial extraction would make the linter quietly wrong.

Usage::

    python tools/sync_odoo.py 17.0 18.0 19.0
    python tools/sync_odoo.py --src-root /tmp/odoo-src 19.0
    python tools/sync_odoo.py --check 17.0 18.0 19.0   # exit 1 if upstream changed semantics
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "src" / "sevlint" / "data"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "odoo"

SPARSE_PATTERNS = [
    "/odoo/__init__.py",
    "/odoo/release.py",
    "/odoo/tools/safe_eval.py",
    "/odoo/addons/base/models/ir_actions.py",
    "/addons/*/models/ir_actions*.py",
]
# Context names passed to safe_eval as wrapped modules (attribute whitelists apply).
WRAPPED_IN_CONTEXT = ("datetime", "dateutil", "time")
# Models whose _get_eval_context feeds ir.actions.server code evaluation.
SERVER_ACTION_MODELS = {"ir.actions.actions", "ir.actions.server"}


class ExtractError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# checkout
# --------------------------------------------------------------------------

def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _write_sparse_patterns(target: Path) -> None:
    sparse = target / ".git" / "info" / "sparse-checkout"
    existing = sparse.read_text().splitlines() if sparse.exists() else []
    sparse.write_text("\n".join(dict.fromkeys(existing + SPARSE_PATTERNS)) + "\n")


def checkout(branch: str, src_root: Path | None) -> Path:
    if src_root is not None:
        target = src_root / f"src-{branch}"
        if (target / ".git").is_dir():
            _write_sparse_patterns(target)
            _run("git", "-C", str(target), "sparse-checkout", "reapply")
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        target = Path(tempfile.mkdtemp(prefix=f"sevlint-odoo-{branch}-"))
        target.rmdir()
    _run("git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--depth", "1",
         "-b", branch, "https://github.com/odoo/odoo.git", str(target))
    _run("git", "-C", str(target), "sparse-checkout", "init", "--no-cone")
    _write_sparse_patterns(target)
    _run("git", "-C", str(target), "checkout", "-q", branch)
    return target


def git_head(path: Path) -> str:
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------------
# safe_eval.py
# --------------------------------------------------------------------------

def _str_list(node: ast.AST, env: dict[str, list[str]]) -> list[str]:
    """Evaluate the list-of-opcode-names expressions used in safe_eval.py."""
    if isinstance(node, ast.List):
        out: list[str] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
            elif isinstance(elt, ast.Starred) and isinstance(elt.value, ast.GeneratorExp):
                out.extend(_prefixed_generator(elt.value, env))
            else:
                raise ExtractError(f"unsupported list element: {ast.unparse(elt)}")
        return out
    if isinstance(node, ast.Name) and node.id in env:
        return list(env[node.id])
    raise ExtractError(f"unsupported list expression: {ast.unparse(node)}")


def _prefixed_generator(gen: ast.GeneratorExp, env: dict[str, list[str]]) -> list[str]:
    """``*('BINARY_' + op for op in _operations)``"""
    if len(gen.generators) != 1:
        raise ExtractError(f"unsupported generator: {ast.unparse(gen)}")
    comp = gen.generators[0]
    elt = gen.elt
    if not (isinstance(comp.target, ast.Name) and isinstance(comp.iter, ast.Name)
            and comp.iter.id in env and not comp.ifs
            and isinstance(elt, ast.BinOp) and isinstance(elt.op, ast.Add)
            and isinstance(elt.left, ast.Constant) and isinstance(elt.left.value, str)
            and isinstance(elt.right, ast.Name) and elt.right.id == comp.target.id):
        raise ExtractError(f"unsupported generator: {ast.unparse(gen)}")
    return [elt.left.value + item for item in env[comp.iter.id]]


def _to_opcodes_arg(node: ast.AST) -> ast.AST:
    """``set(to_opcodes([...]))`` or ``to_opcodes([...])`` -> the list node."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "set":
        (node,) = node.args
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "to_opcodes":
        return node.args[0]
    raise ExtractError(f"expected to_opcodes([...]): {ast.unparse(node)}")


def _module_assigns(tree: ast.Module) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            out[stmt.targets[0].id] = stmt.value
    return out


def extract_safe_eval(source: str) -> dict:
    tree = ast.parse(source)
    assigns = _module_assigns(tree)
    env: dict[str, list[str]] = {}

    def need(name: str) -> ast.AST:
        if name not in assigns:
            raise ExtractError(f"{name} not found in safe_eval.py")
        return assigns[name]

    env["_operations"] = _str_list(need("_operations"), env)
    blacklist = _str_list(_to_opcodes_arg(need("_BLACKLIST")), env)

    # _CONST_OPCODES = set(to_opcodes([...])) - _BLACKLIST
    node = need("_CONST_OPCODES")
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
            and isinstance(node.right, ast.Name) and node.right.id == "_BLACKLIST"):
        raise ExtractError("unexpected _CONST_OPCODES shape")
    const = _str_list(_to_opcodes_arg(node.left), env)

    def union_extra(name: str, base: str) -> list[str]:
        # NAME = BASE.union(to_opcodes([...])) - _BLACKLIST
        node = need(name)
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
                and isinstance(node.right, ast.Name) and node.right.id == "_BLACKLIST"):
            raise ExtractError(f"unexpected {name} shape")
        call = node.left
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "union" and isinstance(call.func.value, ast.Name)
                and call.func.value.id == base and len(call.args) == 1):
            raise ExtractError(f"unexpected {name} shape")
        return _str_list(_to_opcodes_arg(call.args[0]), env)

    expr_extra = union_extra("_EXPR_OPCODES", "_CONST_OPCODES")
    safe_extra = union_extra("_SAFE_OPCODES", "_EXPR_OPCODES")

    unsafe_attributes = ast.literal_eval(need("_UNSAFE_ATTRIBUTES"))

    builtins_node = need("_BUILTINS")
    if not isinstance(builtins_node, ast.Dict):
        raise ExtractError("_BUILTINS is not a dict literal")
    builtins = [ast.literal_eval(k) for k in builtins_node.keys]

    wrapped = _extract_wrapped(tree, assigns)

    return {
        "opcodes": {
            "blacklist": blacklist,
            "const": const,
            "expr_extra": expr_extra,
            "safe_extra": safe_extra,
        },
        "unsafe_attributes": unsafe_attributes,
        "builtins": builtins,
        "wrapped_modules": {k: wrapped[k] for k in WRAPPED_IN_CONTEXT if k in wrapped},
        "algorithm_fingerprint": _algorithm_fingerprint(tree),
    }


def _extract_wrapped(tree: ast.Module, assigns: dict[str, ast.AST]) -> dict[str, dict]:
    """``name = wrap_module(mod, [attrs] | {sub: [attrs]})`` plus later ``a.b.c = ...`` patches."""
    wrapped: dict[str, dict] = {}
    for name, node in assigns.items():
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "wrap_module":
            spec = ast.literal_eval(node.args[1])
            if isinstance(spec, list):
                wrapped[name] = {attr: None for attr in spec}
            elif isinstance(spec, dict):
                wrapped[name] = {attr: list(sub) for attr, sub in spec.items()}
            else:
                raise ExtractError(f"unsupported wrap_module spec for {name}")
    for stmt in tree.body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
            continue
        target = stmt.targets[0]
        chain: list[str] = []
        while isinstance(target, ast.Attribute):
            chain.insert(0, target.attr)
            target = target.value
        if isinstance(target, ast.Name) and target.id in wrapped and chain:
            if len(chain) == 1:
                wrapped[target.id].setdefault(chain[0], None)
            elif len(chain) == 2 and isinstance(wrapped[target.id].get(chain[0]), list):
                if chain[1] not in wrapped[target.id][chain[0]]:
                    wrapped[target.id][chain[0]].append(chain[1])
            else:
                raise ExtractError(f"unsupported patch of wrapped module: {ast.unparse(stmt)}")
    return wrapped


def _algorithm_fingerprint(tree: ast.Module) -> str:
    """Hash of the checking functions, so a changed algorithm is noticed on sync."""
    wanted = {"assert_no_dunder_name", "assert_valid_codeobj", "compile_codeobj", "test_expr", "test_python_expr"}
    parts = []
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name in wanted:
            body = stmt.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]  # ignore docstrings
            parts.append(stmt.name + ":" + ast.dump(ast.Module(body=body, type_ignores=[])))
    return hashlib.sha256("\n".join(sorted(parts)).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# eval contexts
# --------------------------------------------------------------------------

def _context_keys(func: ast.FunctionDef) -> list[str]:
    keys: list[str] = []

    def add_dict(d: ast.Dict) -> None:
        for k in d.keys:
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                raise ExtractError(f"non-literal eval_context key in {func.name}:{func.lineno}")
            keys.append(k.value)

    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            add_dict(node.value)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) \
                        and target.value.id == "eval_context":
                    key = target.slice
                    if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                        raise ExtractError(f"non-literal eval_context key at line {node.lineno}")
                    keys.append(key.value)
            if isinstance(node.value, ast.Dict) and any(
                    isinstance(t, ast.Name) and t.id == "eval_context" for t in node.targets):
                add_dict(node.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "update" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "eval_context":
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    add_dict(arg)
                else:
                    raise ExtractError(f"eval_context.update with non-literal at line {node.lineno}")
    return keys


def _class_models(cls: ast.ClassDef) -> set[str]:
    """Model names from a class body's ``_name`` / ``_inherit`` literals."""
    models: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in ("_name", "_inherit") for t in stmt.targets):
            try:
                value = ast.literal_eval(stmt.value)
            except ValueError:
                continue
            models.update([value] if isinstance(value, str) else value)
    return models


def extract_contexts(src: Path) -> dict:
    core: list[str] = []
    addons: dict[str, list[str]] = {}
    files = [src / "odoo" / "addons" / "base" / "models" / "ir_actions.py"]
    files += sorted((src / "addons").glob("*/models/ir_actions*.py"))
    for path in files:
        tree = ast.parse(path.read_text())
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            if not _class_models(cls) & SERVER_ACTION_MODELS:
                continue
            for func in cls.body:
                if isinstance(func, ast.FunctionDef) and func.name == "_get_eval_context":
                    keys = _context_keys(func)
                    rel = path.relative_to(src)
                    if rel.parts[0] == "odoo":
                        core.extend(k for k in keys if k not in core)
                    elif keys:
                        module = rel.parts[1]
                        for k in keys:
                            addons.setdefault(k, [])
                            if module not in addons[k]:
                                addons[k].append(module)
    if not {"env", "model", "record", "records", "log", "UserError", "uid", "user", "datetime"} <= set(core):
        raise ExtractError(f"core eval context looks incomplete: {core}")
    return {"core": core, "addons": {k: sorted(v) for k, v in sorted(addons.items())}}


def extract_python_range(src: Path) -> dict:
    for rel in ("odoo/release.py", "odoo/__init__.py"):
        path = src / rel
        if not path.exists():
            continue
        found = {}
        for stmt in ast.parse(path.read_text()).body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) \
                    and stmt.targets[0].id in ("MIN_PY_VERSION", "MAX_PY_VERSION"):
                found[stmt.targets[0].id] = list(ast.literal_eval(stmt.value))
        if len(found) == 2:
            return {"min": found["MIN_PY_VERSION"], "max": found["MAX_PY_VERSION"], "source": rel}
    raise ExtractError("MIN_PY_VERSION/MAX_PY_VERSION not found")


# --------------------------------------------------------------------------

def sync(branch: str, src_root: Path | None, check: bool = False) -> bool:
    """Write the data files; with ``check``, only report whether they would change (ignoring the
    commit/sha bookkeeping in ``source``). Returns True when the data is unchanged."""
    src = checkout(branch, src_root)
    safe_eval_path = src / "odoo" / "tools" / "safe_eval.py"
    source = safe_eval_path.read_text()
    data = {
        "odoo_version": branch,
        "source": {
            "repository": "https://github.com/odoo/odoo",
            "branch": branch,
            "commit": git_head(src),
            "safe_eval_sha256": hashlib.sha256(source.encode()).hexdigest(),
        },
        "python": extract_python_range(src),
        **extract_safe_eval(source),
        "context": extract_contexts(src),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"odoo-{branch}.json"
    if check:
        old = json.loads(out.read_text()) if out.exists() else {}
        strip = lambda d: {k: v for k, v in d.items() if k != "source"}  # noqa: E731
        same = strip(old) == strip(data)
        status = "unchanged" if same else "CHANGED (run tools/sync_odoo.py and review)"
        print(f"{branch}: {data['source']['commit'][:12]} {status}")
        return same
    out.write_text(json.dumps(data, indent=1, sort_keys=False) + "\n")
    fixture = FIXTURE_DIR / branch
    fixture.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(safe_eval_path, fixture / "safe_eval.py")
    print(f"{branch}: {data['source']['commit'][:12]} fingerprint={data['algorithm_fingerprint']} -> {out.relative_to(ROOT)}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("branches", nargs="+", help="Odoo branches, e.g. 17.0 18.0 19.0")
    parser.add_argument("--src-root", type=Path, help="reuse/keep checkouts in DIR/src-<branch>")
    parser.add_argument("--check", action="store_true", help="do not write; exit 1 if the extracted data changed")
    args = parser.parse_args(argv)
    if args.check:
        results = [sync(branch, args.src_root, check=True) for branch in args.branches]
        return 0 if all(results) else 1
    for branch in args.branches:
        sync(branch, args.src_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
