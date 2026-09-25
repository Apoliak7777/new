"""Heuristic warnings: code that Odoo accepts but that is very likely a bug."""
from __future__ import annotations

import ast

from .engine import Diagnostic

QUERY_METHODS = {"search", "search_read", "search_count", "search_fetch", "read_group", "_read_group", "name_search"}
WRITE_METHODS = {"write", "create", "unlink", "copy", "message_post", "activity_schedule",
                 "action_archive", "action_unarchive", "toggle_active"}


def _call_attr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _loop_parts(node: ast.AST) -> list[ast.AST]:
    """Parts of a loop that run once per iteration."""
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return [*node.body]
    if isinstance(node, ast.While):
        return [node.test, *node.body]
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return [node.elt, *(c for g in node.generators for c in g.ifs), *(g.iter for g in node.generators[1:])]
    if isinstance(node, ast.DictComp):
        return [node.key, node.value, *(c for g in node.generators for c in g.ifs),
                *(g.iter for g in node.generators[1:])]
    return []


def cr_commit(tree: ast.Module) -> list[Diagnostic]:
    out = []
    for node in ast.walk(tree):
        attr = _call_attr(node)
        if attr in ("commit", "rollback") and isinstance(node.func.value, ast.Attribute) \
                and node.func.value.attr == "cr":
            out.append(Diagnostic(node.lineno, "W301", f"cr.{attr}() inside a server action breaks the transaction: "
                                                       f"partial data survives a later error; let Odoo commit", "warning"))
    return out


def query_in_loop(tree: ast.Module) -> list[Diagnostic]:
    out = []
    reported: set[int] = set()
    for loop in ast.walk(tree):
        for part in _loop_parts(loop):
            for node in ast.walk(part):
                attr = _call_attr(node)
                if attr in QUERY_METHODS and id(node) not in reported:
                    reported.add(id(node))
                    out.append(Diagnostic(node.lineno, "W302", f".{attr}() inside a loop runs one query per iteration; "
                                                               f"query once before the loop (search with `in`, "
                                                               f"mapped/filtered, _read_group)", "warning"))
    return out


def usererror_rollback(tree: ast.Module) -> list[Diagnostic]:
    writes = sorted((node.lineno, _call_attr(node)) for node in ast.walk(tree) if _call_attr(node) in WRITE_METHODS)
    if not writes:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        earlier = sorted({method for line, method in writes if line < node.lineno})
        if isinstance(exc, ast.Name) and exc.id == "UserError" and earlier:
            calls = ", ".join(f".{m}()" for m in earlier)
            out.append(Diagnostic(node.lineno, "W303", f"raise UserError rolls back the earlier {calls}; to keep the "
                                                       f"changes, return a display_notification action instead",
                                  "warning"))
    return out


def cron_record(tree: ast.Module, defined: set[str]) -> list[Diagnostic]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in ("record", "records") and isinstance(node.ctx, ast.Load) \
                and node.id not in defined:
            out.append(Diagnostic(node.lineno, "W304", f"`{node.id}` is None when the action runs from a scheduled "
                                                       f"action (no active_model); use model.search(...)", "warning"))
    return out


def first_record_only(tree: ast.Module, defined: set[str]) -> list[Diagnostic]:
    if "record" in defined:
        return []
    uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)]
    if any(n.id == "records" for n in uses):
        return []
    first = min((n.lineno for n in uses if n.id == "record"), default=None)
    if first is None:
        return []
    return [Diagnostic(first, "W305", "`record` is only the first selected record when the action runs from a list "
                                      "view (the code runs once); use `records` to process the whole selection",
                       "warning")]


def raise_exception(tree: ast.Module) -> list[Diagnostic]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id == "Exception":
                out.append(Diagnostic(node.lineno, "W306", "raise Exception(...) reaches the user as a server error "
                                                           "(safe_eval re-raises it as ValueError); raise UserError "
                                                           "for a readable message", "warning"))
    return out


def run_rules(tree: ast.Module, caller: str, defined: set[str], *, list_bound: bool = False) -> list[Diagnostic]:
    out = cr_commit(tree) + query_in_loop(tree) + usererror_rollback(tree) + raise_exception(tree)
    if caller == "cron":
        out += cron_record(tree, defined)
    elif caller == "server_action" and list_bound:
        out += first_record_only(tree, defined)
    return out
