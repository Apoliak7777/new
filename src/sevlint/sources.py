"""Extract server action code snippets from files."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.parsers import expat

from .profile import CALLERS, normalize_version

CODE_MODELS = {"ir.actions.server", "ir.cron", "base.automation"}
HEADER_RE = re.compile(r"^\s*#\s*sevlint:(?P<body>.*)$")
HEADER_SCAN_LINES = 10


@dataclass
class Snippet:
    path: str
    code: str
    first_line: int  # file line number of the snippet's first line
    caller: str | None = None  # None: not stated by the source
    odoo_version: str | None = None  # from header or manifest
    label: str = ""
    modules: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    disabled: frozenset[str] = frozenset()
    binding: str | None = None  # binding_view_types when offered in the Action menu, e.g. "list,form"
    save_time_only: bool = False  # state is not 'code': Odoo still validates the code on save
    truncated_at: int | None = None  # XML: file line of text Odoo drops (after a comment/child element)


@dataclass
class Header:
    odoo: str | None = None
    caller: str | None = None
    modules: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    disabled: frozenset[str] = frozenset()
    binding: str | None = None
    errors: list[str] = field(default_factory=list)


def _split_list(value: str) -> frozenset[str]:
    return frozenset(v.strip() for v in value.split(",") if v.strip())


def parse_header(text: str) -> Header | None:
    """``# sevlint: odoo=19.0 caller=cron modules=website names=foo,bar disable=W302 binding=list,form``

    Only the leading block of comment/blank lines (at most 10 lines) is a header; a
    ``# sevlint: disable=...`` further down is an inline suppression for its own line.
    """
    header: Header | None = None
    for line in text.splitlines()[:HEADER_SCAN_LINES]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            break  # first statement ends the header block
        match = HEADER_RE.match(line)
        if not match:
            continue
        header = header or Header()
        for token in match.group("body").split():
            key, sep, value = token.partition("=")
            if not sep:
                header.errors.append(f"malformed header token {token!r} (expected key=value)")
                continue
            if key == "odoo":
                header.odoo = normalize_version(value)
            elif key == "caller":
                if value not in CALLERS:
                    header.errors.append(f"unknown caller {value!r} (expected one of {', '.join(CALLERS)})")
                else:
                    header.caller = value
            elif key == "modules":
                header.modules |= _split_list(value)
            elif key == "names":
                header.names |= _split_list(value)
            elif key == "disable":
                header.disabled |= _split_list(value)
            elif key == "binding":
                header.binding = value
            else:
                header.errors.append(f"unknown header key {key!r}")
    return header


def read_python(path: str, text: str, *, require_header: bool) -> tuple[list[Snippet], list[str]]:
    header = parse_header(text)
    if header is None:
        if require_header:
            return [], []
        header = Header()
    snippet = Snippet(
        path=path, code=text, first_line=1,
        caller=header.caller,
        odoo_version=header.odoo,
        modules=header.modules, names=header.names, disabled=header.disabled,
        binding=header.binding,
    )
    return [snippet], header.errors


class _Field:
    def __init__(self, name: str | None, attrs: dict, line: int):
        self.name = name
        self.attrs = attrs
        self.start_line = line
        self.parts: list[str] = []
        self.text_line: int | None = None  # line where the element text starts
        self.depth = 0  # open child elements
        self.closed = False  # a child element or comment was seen: later text is a tail
        self.truncated_at: int | None = None  # first non-blank tail text (dropped by Odoo)


class _Record:
    def __init__(self, model: str | None, xml_id: str, parent: tuple["_Record", str] | None):
        self.model = model
        self.id = xml_id
        self.parent = parent
        self.fields: dict[str, _Field] = {}
        self.current: _Field | None = None


_UNKNOWN = object()


def _value(fld: _Field | None):
    """A field's value as odoo/tools/convert.py sees it: text, ref, or a literal ``eval``."""
    if fld is None:
        return None
    if "eval" in fld.attrs:
        try:
            return ast.literal_eval(fld.attrs["eval"])
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            return _UNKNOWN
    if "ref" in fld.attrs:
        return fld.attrs["ref"]
    return "".join(fld.parts).strip()


def read_xml(path: str, data: bytes) -> tuple[list[Snippet], list[str]]:
    """Server action code in Odoo XML data files, with the text Odoo would store
    (``node.text``: the text before the first child element or comment; last field wins)."""
    if not data.strip():
        return [], []
    parser = expat.ParserCreate()
    snippets: list[Snippet] = []
    stack: list[_Record] = []

    def start(tag, attrs):
        top = stack[-1] if stack else None
        if top is not None and top.current is not None:
            fld = top.current
            fld.closed = True
            if tag == "record" and fld.depth == 0:  # one2many sub-record, e.g. action_server_ids
                stack.append(_Record(attrs.get("model"), attrs.get("id", ""), (top, fld.name or "")))
            else:
                fld.depth += 1
            return
        if tag == "record":
            stack.append(_Record(attrs.get("model"), attrs.get("id", ""), None))
        elif tag == "field" and top is not None:
            top.current = _Field(attrs.get("name"), attrs, parser.CurrentLineNumber)

    def end(tag):
        top = stack[-1] if stack else None
        if top is None:
            return
        if top.current is not None:
            fld = top.current
            if fld.depth:
                fld.depth -= 1
            elif tag == "field":
                top.fields[fld.name or ""] = fld  # a repeated field replaces the earlier one
                top.current = None
            return
        if tag == "record":
            stack.pop()
            _finish_record(path, top, snippets)

    def chars(text):
        top = stack[-1] if stack else None
        if top is None or top.current is None or top.current.depth:
            return
        fld = top.current
        if not fld.closed:
            if fld.text_line is None:
                fld.text_line = parser.CurrentLineNumber
            fld.parts.append(text)
        elif text.strip() and fld.truncated_at is None:
            fld.truncated_at = parser.CurrentLineNumber

    def comment(_data):
        top = stack[-1] if stack else None
        if top is not None and top.current is not None and not top.current.depth:
            top.current.closed = True

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.CommentHandler = comment
    parser.ProcessingInstructionHandler = lambda _target, _data: comment(None)
    try:
        parser.Parse(data, True)
    except expat.ExpatError as err:
        return [], [f"{path}: XML parse error: {err}"]
    return snippets, []


def _finish_record(path: str, record: _Record, snippets: list[Snippet]) -> None:
    fields = record.fields
    code_field = fields.get("code")
    if record.model not in CODE_MODELS or code_field is None:
        return
    if "eval" in code_field.attrs:
        code = _value(code_field)
        if not isinstance(code, str):
            return  # computed in XML; not knowable statically
        first_line, truncated_at = code_field.start_line, None
    else:
        code = "".join(code_field.parts)
        first_line = code_field.text_line or code_field.start_line
        truncated_at = code_field.truncated_at
    if not code.strip():
        return
    state = _value(fields.get("state"))
    parent_model = record.parent[0].model if record.parent else None
    if record.model == "ir.cron":
        caller = "cron"
    elif record.model == "base.automation" or parent_model == "base.automation" or "base_automation_id" in fields:
        caller = "automation"
    else:
        caller = "server_action"
    snippets.append(Snippet(
        path=path, code=code, first_line=first_line, caller=caller, label=record.id,
        binding=_binding(fields),
        save_time_only=isinstance(state, str) and bool(state) and state != "code",
        truncated_at=truncated_at,
    ))


def _binding(fields: dict[str, _Field]) -> str | None:
    """binding_view_types when the action is offered in the Action menu, else None
    (``binding_model_id eval="False"`` unbinds; an unreadable eval means unknown)."""
    model = _value(fields.get("binding_model_id"))
    if model is None or model is _UNKNOWN or model in (False, "", 0):
        return None
    view_types = _value(fields.get("binding_view_types"))
    if view_types is None:
        return "list,form"  # Odoo's default binding_view_types
    return view_types if isinstance(view_types, str) and view_types else None


def find_manifest(path: Path) -> Path | None:
    for parent in [path.parent, *path.parents][:6]:
        manifest = parent / "__manifest__.py"
        if manifest.is_file():
            return manifest
    return None


def _read_manifest(manifest: Path) -> dict:
    try:
        data = ast.literal_eval(manifest.read_text(encoding="utf-8"))
    except (ValueError, SyntaxError, UnicodeDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def manifest_version(path: Path) -> str | None:
    """Odoo series from the nearest __manifest__.py 'version' (e.g. '19.0.1.0.0' -> '19.0')."""
    manifest = find_manifest(path)
    if manifest is None:
        return None
    parts = str(_read_manifest(manifest).get("version", "")).split(".")
    if len(parts) >= 4 and parts[0].isdigit() and int(parts[0]) >= 10:
        return normalize_version(".".join(parts[:2]))
    return None


def manifest_modules(path: Path, max_modules: int = 500) -> frozenset[str]:
    """The module owning ``path`` plus its dependencies, followed through sibling module
    directories of the same addons path. Unresolvable dependencies are still included."""
    manifest = find_manifest(path)
    if manifest is None:
        return frozenset()
    addons_dir = manifest.parent.parent
    seen: set[str] = set()
    todo = [manifest.parent.name]
    while todo and len(seen) < max_modules:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        dep_manifest = addons_dir / name / "__manifest__.py"
        if dep_manifest.is_file():
            depends = _read_manifest(dep_manifest).get("depends", [])
            todo.extend(d for d in depends if isinstance(d, str) and d not in seen)
    return frozenset(seen)
