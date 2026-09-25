"""Checks that mirror (E0xx/E1xx) or predict (E2xx) what Odoo does with server action code.

E0xx/E1xx replicate ``_check_python_code`` -> ``test_python_expr(code.strip(), mode="exec")``:
compile with the running interpreter, then Odoo's ``assert_valid_codeobj`` (forbidden
names in ``co_names``, opcodes outside ``_SAFE_OPCODES``, recursively into nested code
objects). Odoo refuses to save such code.

E2xx are runtime failures that the save-time check does not catch (NameError,
AttributeError on wrapped modules).
"""
from __future__ import annotations

import ast
import dis
import types
import warnings
from dataclasses import dataclass, field

from .profile import Profile

SAVE_TIME = "rejected when saving in Odoo"
RUNTIME = "fails at runtime"

# opname -> (construct, suggestion)
OPCODE_HINTS: dict[str, tuple[str, str]] = {
    "IMPORT_NAME": ("import statement", "use the names Odoo provides (datetime, dateutil, time, env, ...)"),
    "IMPORT_FROM": ("from ... import", "use the names Odoo provides (datetime, dateutil, time, env, ...)"),
    "IMPORT_STAR": ("from ... import *", "use the names Odoo provides"),
    "STORE_ATTR": ("attribute assignment `obj.attr = value`", "use record.write({'attr': value})"),
    "DELETE_ATTR": ("`del obj.attr`", "write False/empty value with record.write()"),
    "STORE_GLOBAL": ("`global` statement or `:=` inside a top-level comprehension",
                     "return values from functions / assign outside the comprehension"),
    "DELETE_GLOBAL": ("`global` statement", "return values from functions instead"),
    "DELETE_SUBSCR": ("`del container[key]`", "use dict.pop(key) / list.pop(index)"),
    "LOAD_ASSERTION_ERROR": ("`assert` statement", "use `if not cond: raise UserError(...)`"),
    "SETUP_WITH": ("`with` statement", "call the methods explicitly"),
    "BEFORE_WITH": ("`with` statement", "call the methods explicitly"),
    "LOAD_SPECIAL": ("`with` statement", "call the methods explicitly"),
    "WITH_EXCEPT_START": ("`with` statement", "call the methods explicitly"),
    "LOAD_BUILD_CLASS": ("class definition", "use dicts and functions"),
    "UNPACK_EX": ("starred assignment `a, *b = ...`", "slice explicitly: a, b = seq[0], seq[1:]"),
    "LIST_TO_TUPLE": ("tuple display with `*` unpacking", "use tuple(list(a) + list(b))"),
    "LOAD_DEREF": ("closure (inner function uses a variable of the enclosing function)",
                   "pass the value as a parameter or move the function to the top level"),
    "STORE_DEREF": ("closure (inner function uses a variable of the enclosing function)",
                    "pass the value as a parameter or move the function to the top level"),
    "LOAD_CLOSURE": ("closure (inner function uses a variable of the enclosing function)",
                     "pass the value as a parameter or move the function to the top level"),
    "MAKE_CELL": ("closure (inner function uses a variable of the enclosing function)",
                  "pass the value as a parameter or move the function to the top level"),
    "COPY_FREE_VARS": ("closure (inner function uses a variable of the enclosing function)",
                       "pass the value as a parameter or move the function to the top level"),
    "SETUP_ANNOTATIONS": ("annotated assignment `x: T = ...`", "drop the annotation"),
    "GET_YIELD_FROM_ITER": ("`yield from`", "loop and yield explicitly"),
    "YIELD_FROM": ("`yield from`", "loop and yield explicitly"),
    "SEND": ("`yield from`", "loop and yield explicitly"),
    "END_SEND": ("`yield from`", "loop and yield explicitly"),
    "CLEANUP_THROW": ("`yield from`", "loop and yield explicitly"),
    "GET_LEN": ("`match` with a sequence/mapping pattern", "use if/elif"),
    "MATCH_CLASS": ("`match` statement", "use if/elif"),
    "MATCH_MAPPING": ("`match` statement", "use if/elif"),
    "MATCH_SEQUENCE": ("`match` statement", "use if/elif"),
    "MATCH_KEYS": ("`match` statement", "use if/elif"),
    "CHECK_EG_MATCH": ("`except*`", "use a plain `except`"),
}


@dataclass(frozen=True, order=True)
class Diagnostic:
    line: int
    code: str
    message: str
    severity: str = field(default="error", compare=False)  # error | warning

    def shifted(self, offset: int) -> "Diagnostic":
        return Diagnostic(self.line + offset, self.code, self.message, self.severity)


@dataclass
class Analysis:
    """Result of compiling a snippet; shared by the engine and the rules."""
    stripped: str
    line_offset: int  # lines removed by .strip() before the first code line
    code: types.CodeType | None = None
    tree: ast.Module | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


def iter_code_objects(code: types.CodeType):
    """The root code object and, recursively, the ones stored in co_consts (like Odoo).

    Recursive on purpose: Odoo's assert_valid_codeobj recurses the same way, so absurdly
    deep nesting raises RecursionError in both (see TooComplex)."""
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from iter_code_objects(const)


def _runtime_code_objects(code: types.CodeType):
    """Code objects whose names are resolved when the action runs. Python 3.14 compiles
    annotations into lazy ``__annotate__`` functions that server action code never calls."""
    return [c for c in iter_code_objects(code) if c.co_name != "__annotate__"]


def _instructions(code: types.CodeType):
    """(instruction, line) pairs. Unlocated instructions (MAKE_CELL/COPY_FREE_VARS before RESUME,
    cells hoisted out of inlined comprehensions) take the line of a located instruction using the
    same name, else the previous line, else the code object's first line."""
    instrs = list(dis.get_instructions(code))
    lines = [_located_line(i) for i in instrs]
    by_name: dict[object, int] = {}
    for instr, line in zip(instrs, lines):
        if line is not None and isinstance(instr.argval, str):
            by_name.setdefault(instr.argval, line)
    current = None
    for instr, line in zip(instrs, lines):
        if line is None:
            if current is not None:
                line = current  # continuation of the current line (3.10 marks only line starts)
            elif isinstance(instr.argval, str):
                line = by_name.get(instr.argval)  # hoisted before the first located instruction
        current = line if line is not None else current
        yield instr, line if line is not None else code.co_firstlineno


def _located_line(instr: dis.Instruction) -> int | None:
    positions = getattr(instr, "positions", None)
    if positions is not None and positions.lineno is not None:
        return positions.lineno
    start = getattr(instr, "line_number", None)  # 3.13+
    if start is None and isinstance(instr.starts_line, int) and not isinstance(instr.starts_line, bool):
        start = instr.starts_line  # 3.10
    return start


def _count_lines(text: str) -> int:
    """Line breaks as the compiler counts them (\\n, \\r\\n, \\r)."""
    return text.count("\n") + text.count("\r") - text.count("\r\n")


def split_lines(text: str) -> list[str]:
    """Lines as the compiler numbers them (str.splitlines also splits on \\f, \\x1c, U+2028, ...)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


class TooComplex(Exception):
    """RecursionError/MemoryError while analysing; Odoo's own compile/check fails the same way."""


def analyse(code_text: str) -> Analysis:
    stripped = code_text.strip()
    leading = code_text[: len(code_text) - len(code_text.lstrip())]
    analysis = Analysis(stripped=stripped, line_offset=_count_lines(leading))
    with warnings.catch_warnings():
        # Odoo runs without -O and with default warning filters: never let the linter's own
        # interpreter flags (PYTHONOPTIMIZE, -W error) change the verdict.
        warnings.simplefilter("ignore")
        try:
            analysis.code = compile(stripped, "", "exec", dont_inherit=True, optimize=0)
        except SyntaxError as err:
            analysis.diagnostics.append(Diagnostic(err.lineno or 1, "E001",
                                                   f"{type(err).__name__}: {err.msg} ({SAVE_TIME})"))
            return analysis
        except Exception as err:  # noqa: BLE001 - Odoo turns any compile() failure into a rejection
            analysis.diagnostics.append(Diagnostic(1, "E001", f"{type(err).__name__} while compiling: "
                                                              f"{str(err)[:200]} ({SAVE_TIME})"))
            return analysis
        try:
            analysis.tree = ast.parse(stripped)
        except (RecursionError, MemoryError, SyntaxError, ValueError):
            analysis.tree = None  # AST-based checks are skipped; bytecode checks still run
    return analysis


ANNOTATION_NAMES = {"__annotate__", "__conditional_annotations__", "__annotations__"}
ANNOTATION_HINT = ("annotated assignment `x: T = ...`", "drop the annotation")


def _first_annotation_line(tree: ast.Module | None) -> int | None:
    """First module-level annotated assignment (those inside functions compile to nothing)."""
    if tree is None:
        return None
    todo, lines = list(tree.body), []
    while todo:
        node = todo.pop()
        if isinstance(node, ast.AnnAssign):
            lines.append(node.lineno)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            todo.extend(ast.iter_child_nodes(node))
    return min(lines, default=None)


def check_save_time(analysis: Analysis, profile: Profile) -> list[Diagnostic]:
    """E101 forbidden opcode, E102 forbidden name — Odoo's assert_valid_codeobj."""
    if analysis.code is None:
        return []
    out: set[Diagnostic] = set()
    annotation_line = _first_annotation_line(analysis.tree)
    try:
        code_objects = list(iter_code_objects(analysis.code))
    except RecursionError as err:
        raise TooComplex("code objects nested too deeply") from err
    module_annotate = {id(c) for c in analysis.code.co_consts
                       if isinstance(c, types.CodeType) and c.co_name == "__annotate__"}  # 3.14
    for code in code_objects:
        forbidden_names = {n for n in code.co_names if "__" in n or n in profile.unsafe_attributes}
        is_annotation = code.co_name == "__annotate__"
        at_module_level = code is analysis.code or id(code) in module_annotate
        for instr, line in _instructions(code):
            about_annotations = is_annotation or instr.argval in ANNOTATION_NAMES or instr.opname == "SETUP_ANNOTATIONS"
            if about_annotations and annotation_line and at_module_level:
                line = annotation_line
            if instr.opcode not in profile.safe_opcodes:
                construct, hint = ANNOTATION_HINT if about_annotations else OPCODE_HINTS.get(instr.opname, (None, None))
                if construct:
                    msg = f"{construct} is not allowed (opcode {instr.opname}); {hint} ({SAVE_TIME})"
                else:
                    msg = f"opcode {instr.opname} is not allowed by safe_eval ({SAVE_TIME})"
                out.add(Diagnostic(line, "E101", msg))
            if forbidden_names and isinstance(instr.argval, str) and instr.argval in forbidden_names \
                    and instr.arg is not None and instr.opcode in dis.hasname:
                out.add(Diagnostic(line, "E102", _forbidden_name_message(instr.argval)))
                forbidden_names.discard(instr.argval)
        for name in sorted(forbidden_names):  # present in co_names but not located
            line = annotation_line if name in ANNOTATION_NAMES and annotation_line else code.co_firstlineno
            out.add(Diagnostic(line, "E102", _forbidden_name_message(name)))
    return sorted(out)


def _forbidden_name_message(name: str) -> str:
    if name == "__doc__":
        return (f"a bare string as the first statement is a docstring and stores '__doc__'; "
                f"use # comments ({SAVE_TIME})")
    if name in ANNOTATION_NAMES:
        return f"annotated assignment `x: T = ...` uses {name!r}; drop the annotation ({SAVE_TIME})"
    reason = "contains '__'" if "__" in name else "is in safe_eval's _UNSAFE_ATTRIBUTES"
    return f"access to forbidden name {name!r} (any name/attribute that {reason}) ({SAVE_TIME})"


LOAD_NAME_OPS = {"LOAD_NAME", "LOAD_GLOBAL", "LOAD_FROM_DICT_OR_GLOBALS"}
STORE_NAME_OPS = {"STORE_NAME", "DELETE_NAME"}
ATTR_OPS = {"LOAD_ATTR", "LOAD_METHOD"}
TRANSPARENT_OPS = {"EXTENDED_ARG", "CACHE", "NOP"}


def defined_toplevel_names(code: types.CodeType) -> set[str]:
    return {i.argval for i in dis.get_instructions(code) if i.opname in STORE_NAME_OPS}


def loaded_names(code: types.CodeType) -> list[tuple[str, int]]:
    """(name, line) of every global/name load, i.e. names resolved in the eval context.
    Function locals, parameters and comprehension variables are fast/cell loads and excluded."""
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int]] = []
    for obj in _runtime_code_objects(code):
        for instr, line in _instructions(obj):
            if instr.opname in LOAD_NAME_OPS:
                key = (instr.argval, line)
                if key not in seen:
                    seen.add(key)
                    out.append(key)
    return out


def attribute_chains(code: types.CodeType, bases: set[str]) -> list[tuple[str, list[str], int]]:
    """``base.a.b`` chains where ``base`` is a global/name load (not a local that shadows it)."""
    out = []
    for obj in _runtime_code_objects(code):
        instrs = [(i, line) for i, line in _instructions(obj) if i.opname not in TRANSPARENT_OPS]
        for idx, (instr, _) in enumerate(instrs):
            if instr.opname not in LOAD_NAME_OPS or instr.argval not in bases:
                continue
            chain, line = [], None
            for nxt, nxt_line in instrs[idx + 1: idx + 3]:
                if nxt.opname not in ATTR_OPS:
                    break
                chain.append(nxt.argval)
                line = line or nxt_line
            if chain:
                out.append((instr.argval, chain, line))
    return out


def check_names(analysis: Analysis, profile: Profile, modules: frozenset[str],
                extra_names: frozenset[str], caller: str = "server_action") -> list[Diagnostic]:
    """E201 undefined name, W210 name provided only by an addon, E202 wrapped-module attribute."""
    if analysis.code is None:
        return []
    if caller == "automation":
        modules = modules | {"base_automation"}  # an automation rule implies the module
    out: list[Diagnostic] = []
    defined = defined_toplevel_names(analysis.code)
    known = profile.builtins | profile.context_core | defined | extra_names
    for name, line in loaded_names(analysis.code):
        if name in known or "__" in name:
            continue
        providers = profile.context_addons.get(name)
        if providers:
            if name == "request" and caller == "cron":
                out.append(Diagnostic(line, "W210", "`request` is an unbound proxy in a scheduled action (there is no "
                                                    "HTTP request); using it raises RuntimeError", "warning"))
            elif name == "payload" and (caller == "cron" or not modules & set(providers)):
                out.append(Diagnostic(line, "W210", "`payload` exists only when base_automation is installed and the "
                                                    "action runs from an HTTP request (webhook); never in a scheduled "
                                                    "run", "warning"))
            elif name != "payload" and not modules & set(providers):
                out.append(Diagnostic(line, "W210", f"`{name}` exists only when module {' or '.join(providers)} is "
                                                    f"installed (declare it with --modules)", "warning"))
            continue
        out.append(Diagnostic(line, "E201", f"name `{name}` is not defined in the server action context "
                                            f"(NameError, {RUNTIME})"))
    wrapped = {m for m in profile.wrapped_modules if m not in defined}
    for base, chain, line in attribute_chains(analysis.code, wrapped):
        allowed = profile.wrapped_modules[base]
        first = chain[0]
        if first not in allowed:
            out.append(Diagnostic(line, "E202", f"`{base}.{first}` is not exposed by Odoo's wrapped `{base}` "
                                                f"(allowed: {', '.join(sorted(allowed))}; AttributeError, {RUNTIME})"))
            continue
        sub = allowed[first]
        if sub is not None and len(chain) > 1 and chain[1] not in sub:
            out.append(Diagnostic(line, "E202", f"`{base}.{first}.{chain[1]}` is not exposed by Odoo's wrapped "
                                                f"`{base}.{first}` (allowed: {', '.join(sorted(sub))}; "
                                                f"AttributeError, {RUNTIME})"))
    return out
