"""Heuristic warnings: code that Odoo accepts but that is very likely a bug."""
from __future__ import annotations

import ast
import types

from . import engine
from .engine import Diagnostic

QUERY_METHODS = {"search", "search_read", "search_count", "search_fetch", "_search", "read_group", "_read_group",
                 "formatted_read_group", "web_read_group", "web_search_read", "name_search"}
WRITE_METHODS = {"write", "create", "unlink", "message_post", "activity_schedule",
                 "action_archive", "action_unarchive", "toggle_active"}
# Calls that run a lambda argument once per record/element.
PER_ITEM_METHODS = {"filtered", "mapped", "sorted", "filtered_domain", "grouped"}
PER_ITEM_BUILTINS = {"map", "filter", "sorted", "min", "max"}
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
LOOPS = (ast.For, ast.AsyncFor, ast.While)


def _call_attr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _walk_no_scopes(node: ast.AST):
    """ast.walk that does not enter function/lambda/class bodies (they do not run where defined)."""
    todo = [node]
    while todo:
        cur = todo.pop()
        yield cur
        if isinstance(cur, SCOPES):
            continue
        todo.extend(ast.iter_child_nodes(cur))


def _in_loop(node: ast.AST, parents: dict) -> bool:
    while node in parents:
        node = parents[node]
        if isinstance(node, SCOPES):
            return False
        if isinstance(node, LOOPS):
            return True
    return False


# --------------------------------------------------------------------------- W301

def cr_commit(tree: ast.Module, caller: str, version: str) -> list[Diagnostic]:
    aliases = set()  # cr = env.cr
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Attribute) and stmt.value.attr == "cr":
            aliases |= {t.id for t in stmt.targets if isinstance(t, ast.Name)}
    parents = _parents(tree)
    out = []
    for node in ast.walk(tree):
        attr = _call_attr(node)
        if attr not in ("commit", "rollback"):
            continue
        receiver = node.func.value
        if not ((isinstance(receiver, ast.Attribute) and receiver.attr == "cr")
                or (isinstance(receiver, ast.Name) and receiver.id in aliases)):
            continue
        if attr == "rollback":
            msg = ("cr.rollback() discards everything this transaction did, including the caller's changes, and "
                   "leaves the ORM cache out of sync with the database")
        elif caller == "cron":
            if _in_loop(node, parents):
                continue  # batch commits in a scheduled action are Odoo's own pattern
            msg = ("cr.commit() outside a batch loop: Odoo commits when the scheduled action ends; "
                   + ("for batches use env['ir.cron']._commit_progress(n)" if float(version) >= 19
                      else "commit only between batches"))
        else:
            msg = "cr.commit() inside a server action: a later error leaves partial data committed; let Odoo commit"
        out.append(Diagnostic(node.lineno, "W301", msg, "warning"))
    return out


# --------------------------------------------------------------------------- W302

def _per_iteration_parts(node: ast.AST) -> list[ast.AST]:
    """Sub-trees of ``node`` that run once per iteration/element."""
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return list(node.body)
    if isinstance(node, ast.While):
        return [node.test, *node.body]
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return [node.elt, *(c for g in node.generators for c in g.ifs), *(g.iter for g in node.generators[1:])]
    if isinstance(node, ast.DictComp):
        return [node.key, node.value, *(c for g in node.generators for c in g.ifs),
                *(g.iter for g in node.generators[1:])]
    if isinstance(node, ast.Call):
        per_item = (isinstance(node.func, ast.Attribute) and node.func.attr in PER_ITEM_METHODS) or \
                   (isinstance(node.func, ast.Name) and node.func.id in PER_ITEM_BUILTINS)
        if per_item:
            args = [*node.args, *(k.value for k in node.keywords)]
            return [a.body for a in args if isinstance(a, ast.Lambda)]
    return []


def _is_batch_query(node: ast.Call, loop: ast.AST) -> bool:
    """``while ...: batch = model.search(domain, limit=N)`` is the batching pattern, not N+1."""
    return isinstance(loop, ast.While) and any(k.arg == "limit" for k in node.keywords)


def query_in_loop(tree: ast.Module) -> list[Diagnostic]:
    querying_helpers = {
        stmt.name for stmt in tree.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_call_attr(n) in QUERY_METHODS for n in ast.walk(stmt))
    }
    out = []
    reported: set[int] = set()
    for loop in ast.walk(tree):
        for part in _per_iteration_parts(loop):
            for node in _walk_no_scopes(part):
                if not isinstance(node, ast.Call) or id(node) in reported:
                    continue
                attr = _call_attr(node)
                if attr in QUERY_METHODS and not _is_batch_query(node, loop):
                    reported.add(id(node))
                    out.append(Diagnostic(node.lineno, "W302", f".{attr}() runs once per iteration; query once "
                                                               f"before the loop (search with `in`, "
                                                               f"mapped/filtered, _read_group)", "warning"))
                elif isinstance(node.func, ast.Name) and node.func.id in querying_helpers:
                    reported.add(id(node))
                    out.append(Diagnostic(node.lineno, "W302", f"{node.func.id}() runs a query and is called once "
                                                               f"per iteration; query once before the loop",
                                          "warning"))
    return out


# --------------------------------------------------------------------------- W303

def _run_before(node: ast.AST, parents: dict) -> list[ast.AST]:
    """Statements that may have run before ``node`` on the same path (same function)."""
    out: list[ast.AST] = []
    while node in parents:
        parent = parents[node]
        for name, value in ast.iter_fields(parent):
            if not isinstance(value, list) or not any(v is node for v in value):
                continue
            idx = next(i for i, v in enumerate(value) if v is node)
            if name != "handlers":  # earlier except clauses did not run
                out.extend(value[:idx])
            if isinstance(parent, LOOPS) and name == "body":
                out.extend(value[idx + 1:])  # ran in earlier iterations
            if isinstance(parent, ast.Try) or type(parent).__name__ == "TryStar":
                if name in ("handlers", "orelse", "finalbody"):
                    out.extend(parent.body)
                if name == "finalbody":
                    out.extend([*parent.handlers, *parent.orelse])
        if isinstance(parent, SCOPES):
            break
        node = parent
    return out


def _is_write(node: ast.AST) -> bool:
    if _call_attr(node) not in WRITE_METHODS:
        return False
    receiver = node.func.value
    return not (isinstance(receiver, ast.Name) and receiver.id == "Command")  # Command.create() builds a tuple


def usererror_rollback(tree: ast.Module) -> list[Diagnostic]:
    parents = _parents(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if not (isinstance(exc, ast.Name) and exc.id == "UserError"):
            continue
        earlier = sorted({n.func.attr for stmt in _run_before(node, parents)
                          for n in _walk_no_scopes(stmt) if _is_write(n)})
        if earlier:
            calls = ", ".join(f".{m}()" for m in earlier)
            out.append(Diagnostic(node.lineno, "W303", f"raise UserError rolls back the earlier {calls}; to keep "
                                                       f"the changes, assign action = {{'type': "
                                                       f"'ir.actions.client', 'tag': 'display_notification', ...}} "
                                                       f"instead of raising", "warning"))
    return out


# --------------------------------------------------------------------------- W304 / W305

def _context_loads(code: types.CodeType, name: str) -> list[int]:
    """Lines where ``name`` is read from the eval context: global/name loads (locals,
    parameters and comprehension variables excluded), and top-level reads that happen
    before the first top-level assignment of the same name."""
    stores = [line for instr, line in engine._instructions(code)
              if instr.opname == "STORE_NAME" and instr.argval == name]
    first_store = min(stores, default=None)
    lines = []
    for obj in engine._runtime_code_objects(code):
        for instr, line in engine._instructions(obj):
            if instr.opname in engine.LOAD_NAME_OPS and instr.argval == name:
                if first_store is None or (obj is code and line < first_store):
                    lines.append(line)
    return sorted(set(lines))


def cron_record(code: types.CodeType) -> list[Diagnostic]:
    out = []
    for name in ("record", "records"):
        for line in _context_loads(code, name)[:1]:
            out.append(Diagnostic(line, "W304", f"`{name}` is None when the action runs from a scheduled action "
                                                f"(no active_model); use model.search(...)", "warning"))
    return out


def first_record_only(code: types.CodeType) -> list[Diagnostic]:
    record = _context_loads(code, "record")
    if not record or _context_loads(code, "records"):
        return []
    return [Diagnostic(record[0], "W305", "`record` is only the first selected record when the action runs from a "
                                          "list/kanban view (the code runs once); use `records` to process the "
                                          "whole selection", "warning")]


# --------------------------------------------------------------------------- W306

def _catches_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    types_ = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(t, ast.Name) and t.id == "Exception" for t in types_)


def _caught_locally(node: ast.AST, parents: dict) -> bool:
    child = node
    while child in parents:
        parent = parents[child]
        if isinstance(parent, SCOPES):
            return False
        if isinstance(parent, ast.Try) and any(child is s for s in parent.body) \
                and any(_catches_exception(h) for h in parent.handlers):
            return True
        child = parent
    return False


def raise_exception(tree: ast.Module) -> list[Diagnostic]:
    parents = _parents(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id == "Exception" and not _caught_locally(node, parents):
                out.append(Diagnostic(node.lineno, "W306", "raise Exception(...) reaches the user as a server error "
                                                           "(safe_eval re-raises it as ValueError); raise UserError "
                                                           "for a readable message", "warning"))
    return out


# ---------------------------------------------------------------------------

def run_rules(tree: ast.Module, code: types.CodeType, caller: str, defined: set[str], *,
              list_bound: bool = False, version: str = "19.0") -> list[Diagnostic]:
    out = cr_commit(tree, caller, version) + query_in_loop(tree) + usererror_rollback(tree) + raise_exception(tree)
    if caller == "cron":
        out += cron_record(code)
    elif caller == "server_action" and list_bound:
        out += first_record_only(code)
    return out
