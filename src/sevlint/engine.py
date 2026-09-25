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
    """The root code object and, recursively, the ones stored in co_consts (like Odoo)."""
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from iter_code_objects(const)


def _instructions(code: types.CodeType):
    """(instruction, line) pairs for every instruction; line may be None."""
    current = None
    for instr in dis.get_instructions(code):
        positions = getattr(instr, "positions", None)
        line = positions.lineno if positions is not None and positions.lineno is not None else None
        if line is None:
            start = getattr(instr, "line_number", None)  # 3.13+
            if start is None:
                start = instr.starts_line if isinstance(instr.starts_line, int) and not isinstance(instr.starts_line, bool) else None
            line = start if start is not None else current
        current = line if line is not None else current
        yield instr, line


def analyse(code_text: str) -> Analysis:
    stripped = code_text.strip()
    leading = code_text[: len(code_text) - len(code_text.lstrip())]
    analysis = Analysis(stripped=stripped, line_offset=leading.count("\n"))
    try:
        analysis.code = compile(stripped, "", "exec", dont_inherit=True)
    except SyntaxError as err:
        what = type(err).__name__
        line = err.lineno or 1
        analysis.diagnostics.append(Diagnostic(line, "E001", f"{what}: {err.msg} ({SAVE_TIME})"))
        return analysis
    except (TypeError, ValueError) as err:
        analysis.diagnostics.append(Diagnostic(1, "E001", f"{type(err).__name__}: {err} ({SAVE_TIME})"))
        return analysis
    analysis.tree = ast.parse(stripped)
    return analysis


def check_save_time(analysis: Analysis, profile: Profile) -> list[Diagnostic]:
    """E101 forbidden opcode, E102 forbidden name — Odoo's assert_valid_codeobj."""
    if analysis.code is None:
        return []
    out: set[Diagnostic] = set()
    for code in iter_code_objects(analysis.code):
        forbidden_names = {n for n in code.co_names if "__" in n or n in profile.unsafe_attributes}
        for instr, line in _instructions(code):
            if instr.opcode not in profile.safe_opcodes:
                construct, hint = OPCODE_HINTS.get(instr.opname, (None, None))
                if construct:
                    msg = f"{construct} is not allowed (opcode {instr.opname}); {hint} ({SAVE_TIME})"
                else:
                    msg = f"opcode {instr.opname} is not allowed by safe_eval ({SAVE_TIME})"
                out.add(Diagnostic(line or 1, "E101", msg))
            if forbidden_names and isinstance(instr.argval, str) and instr.argval in forbidden_names \
                    and instr.arg is not None and instr.opcode in dis.hasname:
                out.add(Diagnostic(line or 1, "E102", _forbidden_name_message(instr.argval)))
                forbidden_names.discard(instr.argval)
        for name in sorted(forbidden_names):  # present in co_names but not located
            out.add(Diagnostic(1, "E102", _forbidden_name_message(name)))
    return sorted(out)


def _forbidden_name_message(name: str) -> str:
    if name == "__doc__":
        return (f"a bare string as the first statement is a docstring and stores '__doc__'; "
                f"use # comments ({SAVE_TIME})")
    reason = "contains '__'" if "__" in name else "is in safe_eval's _UNSAFE_ATTRIBUTES"
    return f"access to forbidden name {name!r} (any name/attribute that {reason}) ({SAVE_TIME})"


LOAD_NAME_OPS = {"LOAD_NAME", "LOAD_GLOBAL", "LOAD_FROM_DICT_OR_GLOBALS"}
STORE_NAME_OPS = {"STORE_NAME", "DELETE_NAME"}


def defined_toplevel_names(code: types.CodeType) -> set[str]:
    return {i.argval for i in dis.get_instructions(code) if i.opname in STORE_NAME_OPS}


def loaded_names(code: types.CodeType) -> list[tuple[str, int]]:
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int]] = []
    for obj in iter_code_objects(code):
        for instr, line in _instructions(obj):
            if instr.opname in LOAD_NAME_OPS:
                key = (instr.argval, line or 1)
                if key not in seen:
                    seen.add(key)
                    out.append(key)
    return out


def check_names(analysis: Analysis, profile: Profile, modules: frozenset[str],
                extra_names: frozenset[str]) -> list[Diagnostic]:
    """E201 undefined name, W210 name provided only by an addon, E202 wrapped-module attribute."""
    if analysis.code is None:
        return []
    out: list[Diagnostic] = []
    defined = defined_toplevel_names(analysis.code)
    known = profile.builtins | profile.context_core | defined | extra_names
    for name, line in loaded_names(analysis.code):
        if name in known or "__" in name:
            continue
        providers = profile.context_addons.get(name)
        if providers:
            if not modules & set(providers):
                out.append(Diagnostic(line, "W210", f"`{name}` exists only when module {' or '.join(providers)} is installed "
                                                     f"(declare it with --modules)", "warning"))
            continue
        out.append(Diagnostic(line, "E201", f"name `{name}` is not defined in the server action context "
                                            f"(NameError, {RUNTIME})"))
    if analysis.tree is not None:
        out.extend(_check_wrapped(analysis.tree, profile, defined))
    return out


def _check_wrapped(tree: ast.Module, profile: Profile, defined: set[str]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    inner_nodes: set[int] = set()  # ast.walk yields a chain's outermost Attribute first
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in inner_nodes:
            continue
        chain = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            chain.insert(0, cur.attr)
            if cur is not node:
                inner_nodes.add(id(cur))
            cur = cur.value
        if not isinstance(cur, ast.Name) or cur.id not in profile.wrapped_modules or cur.id in defined:
            continue
        allowed = profile.wrapped_modules[cur.id]
        first = chain[0]
        if first not in allowed:
            out.append(Diagnostic(node.lineno, "E202", f"`{cur.id}.{first}` is not exposed by Odoo's wrapped `{cur.id}` "
                                                       f"(allowed: {', '.join(sorted(allowed))}; AttributeError, {RUNTIME})"))
            continue
        sub = allowed[first]
        if sub is not None and len(chain) > 1 and chain[1] not in sub:
            out.append(Diagnostic(node.lineno, "E202", f"`{cur.id}.{first}.{chain[1]}` is not exposed by Odoo's wrapped "
                                                       f"`{cur.id}.{first}` (allowed: {', '.join(sorted(sub))}; "
                                                       f"AttributeError, {RUNTIME})"))
    return out
