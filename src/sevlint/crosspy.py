"""W110: code whose save-time verdict depends on the Python version the Odoo server runs.

Odoo checks the bytecode of the Python it runs on; sevlint compiles with its own. These
constructs compile to opcodes outside ``_SAFE_OPCODES`` on some Python versions only (each
verified against Odoo's real safe_eval on 3.10-3.14, see tests/test_cross_python.py):

* a list/set/dict comprehension that reads a variable of an enclosing function, lambda or
  comprehension, or contains ``:=``: a closure before 3.12 (PEP 709 inlines comprehensions)
* ``(*a, b)`` / ``f(x, *a)``: LIST_TO_TUPLE before 3.12
* ``a @ b``: BINARY_MATRIX_MULTIPLY on 3.10
* ``assert``: LOAD_ASSERTION_ERROR before 3.14
* syntax a Python version does not have yet (``except*``, ``type X = ...``, PEP 701 f-strings)
"""
from __future__ import annotations

import ast
import sys
import warnings

from .engine import Analysis, Diagnostic
from .profile import Profile

KNOWN = [(3, 10), (3, 11), (3, 12), (3, 13), (3, 14)]
BEFORE_312 = frozenset({(3, 10), (3, 11)})
FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp)
SCOPES = FUNCTION_SCOPES + COMPREHENSIONS + (ast.GeneratorExp,)


def _span(versions: set[tuple[int, int]]) -> str:
    ordered = sorted(versions)
    if not ordered:
        return ""
    text = ".".join(map(str, ordered[0]))
    return text if len(ordered) == 1 else f"{text}-{'.'.join(map(str, ordered[-1]))}"


def _parents(tree: ast.AST) -> dict:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _walk_region(node: ast.AST, skip_scopes=SCOPES):
    """Nodes evaluated in ``node``'s own scope (not descending into nested scopes)."""
    todo = list(ast.iter_child_nodes(node))
    while todo:
        cur = todo.pop()
        yield cur
        if not isinstance(cur, skip_scopes):
            todo.extend(ast.iter_child_nodes(cur))


def _comprehension_region(comp: ast.AST) -> list[ast.AST]:
    """Parts of a comprehension evaluated inside its own scope (all but the first iterable)."""
    parts = [comp.key, comp.value] if isinstance(comp, ast.DictComp) else [comp.elt]
    for i, gen in enumerate(comp.generators):
        parts += [gen.target, *gen.ifs] + ([gen.iter] if i else [])
    return parts


def _bound_in(scope: ast.AST) -> set[str]:
    """Names local to a function/lambda/comprehension scope."""
    names: set[str] = set()
    if isinstance(scope, FUNCTION_SCOPES):
        args = scope.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if arg is not None:
                names.add(arg.arg)
        declared = set()
        body = scope.body if isinstance(scope.body, list) else [scope.body]
        for stmt in body:
            for node in [stmt, *_walk_region(stmt)]:
                if isinstance(node, (ast.Global, ast.Nonlocal)):
                    declared.update(node.names)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                    names.add(node.id)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(node.name)
                elif isinstance(node, ast.ExceptHandler) and node.name:
                    names.add(node.name)
                elif isinstance(node, ast.NamedExpr):
                    names.add(node.target.id)
        return names - declared
    for gen in scope.generators:
        names |= {n.id for n in ast.walk(gen.target) if isinstance(n, ast.Name)}
    return names


def _free_names(comp: ast.AST) -> set[str]:
    """Names a comprehension reads from enclosing scopes (its own targets excluded)."""
    loads: set[str] = set()
    for part in _comprehension_region(comp):
        for node in [part, *_walk_region(part, skip_scopes=FUNCTION_SCOPES)]:
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loads.add(node.id)
    bound = _bound_in(comp)
    for node in ast.walk(comp):  # nested comprehensions bind their own targets
        if node is not comp and isinstance(node, COMPREHENSIONS + (ast.GeneratorExp,)):
            bound |= _bound_in(node)
    return loads - bound


def comprehension_closures(tree: ast.Module) -> list[tuple[int, str]]:
    parents = _parents(tree)
    out = []
    for comp in ast.walk(tree):
        if not isinstance(comp, COMPREHENSIONS):
            continue
        enclosing: list[ast.AST] = []
        node = comp
        while node in parents:
            node = parents[node]
            if isinstance(node, SCOPES):
                enclosing.append(node)
        if not enclosing:
            continue  # module level: outer names are globals, no closure
        outer_locals = set().union(*(_bound_in(scope) for scope in enclosing))
        captured = sorted(_free_names(comp) & outer_locals)
        walrus = any(isinstance(n, ast.NamedExpr) for part in _comprehension_region(comp) for n in ast.walk(part))
        if captured or walrus:
            what = f"reads `{captured[0]}` of the enclosing scope" if captured else "uses `:=`"
            out.append((comp.lineno, f"a comprehension inside a function, lambda or comprehension that {what} "
                                     f"(a closure before Python 3.12)"))
    return out


def starred_tuples(tree: ast.Module) -> list[tuple[int, str]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and isinstance(node.ctx, ast.Load) \
                and any(isinstance(e, ast.Starred) for e in node.elts):
            out.append((node.lineno, "a tuple display with `*` unpacking"))
        elif isinstance(node, ast.Call) and len(node.args) >= 2 and any(isinstance(a, ast.Starred) for a in node.args):
            out.append((node.lineno, "a call mixing `*args` with other positional arguments"))
    return out


def matmul(tree: ast.Module) -> list[tuple[int, str]]:
    return [(n.lineno, "the `@` operator") for n in ast.walk(tree)
            if isinstance(n, (ast.BinOp, ast.AugAssign)) and isinstance(n.op, ast.MatMult)]


def asserts(tree: ast.Module) -> list[tuple[int, str]]:
    # The compiler drops `assert <truthy constant>`, which then needs no opcode at all.
    return [(n.lineno, "an `assert` statement") for n in ast.walk(tree)
            if isinstance(n, ast.Assert) and not (isinstance(n.test, ast.Constant) and n.test.value)]


def pep701_fstrings(tree: ast.Module, source: str) -> list[tuple[int, str]]:
    """f-strings reusing their quote or a backslash inside {} (valid from Python 3.12 only)."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        segment = ast.get_source_segment(source, node) or ""
        body = segment.lstrip("rRfFbBuU")
        quote = body[:3] if body[:3] in ('"""', "'''") else body[:1]
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                expr = ast.get_source_segment(source, value.value) or ""
                if (quote and quote in expr) or "\\" in expr:
                    out.append((node.lineno, "an f-string reusing its quotes or a backslash inside `{}`"))
                    break
    return out


def newer_syntax(stripped: str, versions: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    """Pythons whose grammar rejects the code (except*, type X = ..., generics, t-strings)."""
    rejected = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a SyntaxWarning under -W error is not a grammar difference
        for version in versions:
            try:
                ast.parse(stripped, feature_version=version)
            except SyntaxError as err:
                rejected[version] = err.lineno or 1
    return rejected


def _supported(profile: Profile) -> set[tuple[int, int]]:
    return {v for v in KNOWN if v >= profile.python_min and (profile.python_max is None or v <= profile.python_max)}


def findings(analysis: Analysis, profile: Profile) -> list[tuple[int, str, frozenset]]:
    """(line, construct, Pythons among the profile's supported ones that reject it)."""
    if analysis.tree is None:
        return []
    running = sys.version_info[:2]
    supported = _supported(profile)
    tree = analysis.tree
    found: list[tuple[int, str, frozenset]] = []
    found += [(line, what, BEFORE_312) for line, what in comprehension_closures(tree)]
    found += [(line, what, BEFORE_312) for line, what in starred_tuples(tree)]
    found += [(line, what, frozenset({(3, 10)})) for line, what in matmul(tree)]
    found += [(line, what, frozenset(KNOWN[:4])) for line, what in asserts(tree)]
    found += [(line, what, BEFORE_312) for line, what in pep701_fstrings(tree, analysis.stripped)]
    syntax = newer_syntax(analysis.stripped, [v for v in sorted(supported) if v < running])
    if syntax:
        found.append((min(syntax.values()), "syntax these Python versions do not have yet", frozenset(syntax)))
    return [(line, what, frozenset(rejected & supported)) for line, what, rejected in found if rejected & supported]


def check_cross_python(analysis: Analysis, profile: Profile, target_python: str | None) -> list[Diagnostic]:
    """W110 for constructs Odoo would reject on another Python the target Odoo version supports."""
    if target_python:
        return []  # a pinned target is enforced to be the running Python: the verdict is exact
    running = sys.version_info[:2]
    out = []
    for line, what, bad in findings(analysis, profile):
        if running in bad:
            continue  # the running Python reports it as an error already
        out.append(Diagnostic(line, "W110", f"Odoo {profile.odoo_version} on Python {_span(set(bad))} rejects {what}; "
                                            f"it is fine on Python {'.'.join(map(str, running))}. Set target-python "
                                            f"to the server's Python for an exact verdict", "warning"))
    return out
