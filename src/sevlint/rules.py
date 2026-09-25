"""Heuristic warnings: code that Odoo accepts but that is very likely a bug."""
from __future__ import annotations

import ast
import types

from . import engine, profile as profiles
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


def _in_loop(node: ast.AST, parents: dict, called_in_loop: set[str] = frozenset()) -> bool:
    """Inside a loop of the same function, or inside a top-level helper that is called from one."""
    while node in parents:
        node = parents[node]
        if isinstance(node, SCOPES):
            return getattr(node, "name", None) in called_in_loop and parents.get(node) is not None \
                and isinstance(parents[node], ast.Module)
        if isinstance(node, LOOPS):
            return True
    return False


def _helpers_called_in_loops(tree: ast.Module, parents: dict) -> set[str]:
    names = {s.name for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {n.func.id for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in names
            and _in_loop(n, parents)}


# --------------------------------------------------------------------------- W301

def cr_commit(tree: ast.Module, caller: str, version: str) -> list[Diagnostic]:
    aliases = set()  # cr = env.cr
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Attribute) and stmt.value.attr == "cr":
            aliases |= {t.id for t in stmt.targets if isinstance(t, ast.Name)}
    parents = _parents(tree)
    called_in_loop = _helpers_called_in_loops(tree, parents) if caller == "cron" else set()
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
            if _in_loop(node, parents, called_in_loop):
                continue  # batch commits in a scheduled action are Odoo's own pattern
            msg = ("cr.commit() outside a batch loop: Odoo commits when the scheduled action ends; "
                   + ("for batches use env['ir.cron']._commit_progress(n)" if profiles.version_key(version) >= (19, 0)
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
        batched = any(_call_attr(n) in QUERY_METHODS and any(k.arg == "limit" for k in n.keywords)
                      for stmt in node.body for n in ast.walk(stmt))
        return [*([] if batched else [node.test]), *node.body]  # a count per batch is not N+1
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

def _is_write(node: ast.AST) -> bool:
    if _call_attr(node) not in WRITE_METHODS:
        return False
    receiver = node.func.value
    return not (isinstance(receiver, ast.Name) and receiver.id == "Command")  # Command.create() builds a tuple


class _Writes:
    """Write calls per subtree, memoised. Descends into lambdas (usually run on the spot by
    filtered/mapped/sorted) but not into def/class bodies; calls to top-level helpers that
    write count as writes."""

    def __init__(self, tree: ast.Module):
        self.memo: dict[int, frozenset[str]] = {}
        self.prefixes: dict[int, list[frozenset[str]]] = {}
        self.helpers: set[str] = set()
        defs = [s for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for _ in range(3):  # helpers calling helpers
            self.memo.clear()
            self.helpers |= {d.name for d in defs if any(self.of(stmt) for stmt in d.body)}
        self.memo.clear()

    def of(self, node: ast.AST) -> frozenset[str]:
        key = id(node)
        if key not in self.memo:
            found: set[str] = set()
            todo = [node]
            while todo:
                cur = todo.pop()
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if _is_write(cur):
                    found.add(f".{cur.func.attr}()")
                elif isinstance(cur, ast.Call) and isinstance(cur.func, ast.Name) and cur.func.id in self.helpers:
                    found.add(f"{cur.func.id}()")
                todo.extend(ast.iter_child_nodes(cur))
            self.memo[key] = frozenset(found)
        return self.memo[key]

    def prefix(self, stmts: list, end: int) -> frozenset[str]:
        """Writes in stmts[:end], via cached prefix unions (linear per block, not per raise)."""
        key = id(stmts)
        if key not in self.prefixes:
            acc, pref = frozenset(), [frozenset()]
            for stmt in stmts:
                acc = acc | self.of(stmt)
                pref.append(acc)
            self.prefixes[key] = pref
        return self.prefixes[key][end]


HEADER_FIELDS = ("test", "iter", "subject")  # If/While.test, For.iter, Match.subject run before the body


def _writes_before(node: ast.AST, parents: dict, writes: _Writes) -> tuple[set[str], ast.AST | None]:
    """Writes that may have run before ``node`` on the same path, and the enclosing function
    (or None at module level)."""
    out: set[str] = set()
    child = node
    while child in parents:
        parent = parents[child]
        for header in HEADER_FIELDS:
            value = getattr(parent, header, None)
            if isinstance(value, ast.AST) and value is not child:
                out |= writes.of(value)
        for name, value in ast.iter_fields(parent):
            if not isinstance(value, list):
                continue
            idx = next((i for i, v in enumerate(value) if v is child), None)
            if idx is None:
                continue
            if isinstance(parent, LOOPS) and name in ("body", "orelse"):
                out |= writes.prefix(parent.body, len(parent.body))  # earlier iterations, any branch
            elif name not in ("handlers", "cases"):  # other except clauses / match cases did not run
                out |= writes.prefix(value, idx)
            if isinstance(parent, ast.Try) or type(parent).__name__ == "TryStar":
                if name in ("handlers", "orelse", "finalbody"):
                    out |= writes.prefix(parent.body, len(parent.body))
                if name == "finalbody":
                    out |= writes.prefix(parent.handlers, len(parent.handlers))
                    out |= writes.prefix(parent.orelse, len(parent.orelse))
        if isinstance(parent, SCOPES):
            return out, parent
        child = parent
    return out, None


def _catches(handler: ast.ExceptHandler, names: set[str]) -> bool:
    if handler.type is None:
        return True
    types_ = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(t, ast.Name) and t.id in names for t in types_)


def _caught_locally(node: ast.AST, parents: dict, names: set[str]) -> bool:
    """Raised inside a ``try`` body (same function) whose handlers catch it."""
    child = node
    while child in parents:
        parent = parents[child]
        if isinstance(parent, SCOPES):
            return False
        if isinstance(parent, ast.Try) and any(child is s for s in parent.body) \
                and any(_catches(h, names) for h in parent.handlers):
            return True
        child = parent
    return False


def usererror_rollback(tree: ast.Module) -> list[Diagnostic]:
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise) and n.exc is not None
              and isinstance(n.exc.func if isinstance(n.exc, ast.Call) else n.exc, ast.Name)
              and (n.exc.func if isinstance(n.exc, ast.Call) else n.exc).id == "UserError"]
    if not raises or not any(_is_write(n) for n in ast.walk(tree)):
        return []
    parents = _parents(tree)
    writes = _Writes(tree)
    top_defs = {s.name: s for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
    calls_to: dict[str, list[ast.Call]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in top_defs:
            calls_to.setdefault(n.func.id, []).append(n)
    out = []
    for node in raises:
        if _caught_locally(node, parents, {"UserError", "Exception"}):
            continue
        earlier, scope = _writes_before(node, parents, writes)
        if scope is not None and getattr(scope, "name", None) in top_defs and top_defs[scope.name] is scope:
            for call in calls_to.get(scope.name, []):  # a raise in a helper runs where it is called
                if not any(p is scope for p in _ancestors(call, parents)):
                    earlier |= _writes_before(call, parents, writes)[0]
        if earlier:
            out.append(Diagnostic(node.lineno, "W303", f"raise UserError rolls back the earlier "
                                                       f"{', '.join(sorted(earlier))}; to keep the changes, assign "
                                                       f"action = {{'type': 'ir.actions.client', 'tag': "
                                                       f"'display_notification', ...}} instead of raising", "warning"))
    return out


def _ancestors(node: ast.AST, parents: dict):
    while node in parents:
        node = parents[node]
        yield node


# --------------------------------------------------------------------------- W304 / W305

def _context_loads(code: types.CodeType, name: str) -> list[int]:
    """Lines where ``name`` is read from the eval context: global/name loads (locals,
    parameters and comprehension variables excluded). Once the top-level code assigns the
    name, only top-level loads executed before that store (by bytecode offset) count."""
    top = list(engine._instructions(code))
    first_store = min((i.offset for i, _ in top if i.opname == "STORE_NAME" and i.argval == name), default=None)
    lines = []
    for obj in engine._runtime_code_objects(code):
        for instr, line in (top if obj is code else engine._instructions(obj)):
            if instr.opname in engine.LOAD_NAME_OPS and instr.argval == name:
                if first_store is None or (obj is code and instr.offset < first_store):
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

def raise_exception(tree: ast.Module) -> list[Diagnostic]:
    parents = _parents(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id == "Exception" and not _caught_locally(node, parents, {"Exception"}):
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
