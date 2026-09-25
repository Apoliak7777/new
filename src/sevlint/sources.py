"""Extract server action code snippets from files."""
from __future__ import annotations

import ast
import codecs
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
    # findings about the XML itself: (file line, code, severity, message)
    source_findings: list[tuple[int, str, str, str]] = field(default_factory=list)


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
            if token == "disable":
                continue  # a bare inline suppression on a comment line: nothing to suppress
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


INLINE_DISABLE_RE = re.compile(r"#\s*sevlint:\s*disable(?:=(?P<codes>[\w,]+))?")
XML_DECL_RE = re.compile(rb"""^\s*<\?xml[^>]*?encoding\s*=\s*["']([A-Za-z0-9._:-]+)["']""")


class _Field:
    def __init__(self, name: str | None, attrs: dict, line: int):
        self.name = name
        self.attrs = attrs
        self.start_line = line
        self.parts: list[str] = []
        self.text_line: int | None = None  # line where the element text starts
        self.depth = 0  # open child elements
        self.closed = False  # a child element or comment was seen: later text is a tail
        self.tail_parts: list[str] = []
        self.truncated_at: int | None = None  # first non-blank tail text (dropped by Odoo)
        self.child_element_line: int | None = None  # a non-<record> child element


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
        except Exception:  # noqa: BLE001 - any non-literal (or unhashable literal) is unknown
            return _UNKNOWN
    if "ref" in fld.attrs:
        return fld.attrs["ref"]
    return "".join(fld.parts).strip()


def decode_xml(data: bytes) -> str:
    """Decode with the declared encoding using Python's codecs (expat alone knows only a few
    single-byte encodings and rejects aliases such as 'utf8' that libxml2 accepts)."""
    for bom, encoding in ((codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16"),
                          (codecs.BOM_UTF16_BE, "utf-16")):
        if data.startswith(bom):
            return data.decode(encoding if encoding != "utf-8" else "utf-8-sig")
    match = XML_DECL_RE.match(data)
    encoding = match.group(1).decode("ascii") if match else "utf-8"
    if not codecs.lookup(encoding)._is_text_encoding:
        raise LookupError(f"{encoding!r} is not a text encoding")
    return data.decode(encoding)


def read_xml(path: str, data: bytes) -> tuple[list[Snippet], list[str]]:
    """Server action code in Odoo XML data files, with the text Odoo would store
    (``node.text``: the text before the first child element or comment; last field wins)."""
    if not data.strip():
        return [], []
    try:
        text = decode_xml(data)
    except (LookupError, UnicodeError, ValueError) as err:
        return [], [f"{path}: cannot decode XML: {err}"]
    parser = expat.ParserCreate(encoding="UTF-8")  # overrides the (already applied) declaration
    snippets: list[Snippet] = []
    problems: list[str] = []
    stack: list[_Record] = []

    def start(tag, attrs):
        top = stack[-1] if stack else None
        if top is not None and top.current is not None:
            fld = top.current
            fld.closed = True
            if tag == "record" and fld.depth == 0:  # one2many sub-record, e.g. action_server_ids
                stack.append(_Record(attrs.get("model"), attrs.get("id", ""), (top, fld.name or "")))
            else:
                if fld.depth == 0 and fld.child_element_line is None:
                    fld.child_element_line = parser.CurrentLineNumber
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
            _finish_record(path, top, snippets, problems)

    def chars(chunk):
        top = stack[-1] if stack else None
        if top is None or top.current is None or top.current.depth:
            return
        fld = top.current
        if not fld.closed:
            if fld.text_line is None:
                fld.text_line = parser.CurrentLineNumber
            fld.parts.append(chunk)
        else:
            if chunk.strip() and fld.truncated_at is None:
                fld.truncated_at = parser.CurrentLineNumber + chunk[:len(chunk) - len(chunk.lstrip())].count("\n")
            fld.tail_parts.append(chunk)

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
        parser.Parse(text.encode("utf-8"), True)
    except expat.ExpatError as err:
        return [], [f"{path}: XML parse error: {err}"]
    except Exception as err:  # noqa: BLE001 - never let one file abort the run
        return [], [f"{path}: cannot read XML: {type(err).__name__}: {err}"]
    return snippets, problems


def _tail_suppressed(fld: _Field) -> bool:
    first = next((line for line in "".join(fld.tail_parts).splitlines() if line.strip()), "")
    match = INLINE_DISABLE_RE.search(first)
    return bool(match) and (match.group("codes") is None or "W100" in match.group("codes").split(","))


def _code_from_file(path: str, fld: _Field, problems: list[str]) -> tuple[str, str] | None:
    """``<field name="code" file="module/path.py"/>``: resolved against the addons directory."""
    manifest = find_manifest(Path(path).absolute())
    target = (manifest.parent.parent / fld.attrs["file"]) if manifest else Path(fld.attrs["file"])
    try:
        return str(target), target.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as err:
        problems.append(f"{path}:{fld.start_line}: cannot read code file {fld.attrs['file']!r} ({err.strerror or err})")
        return None


def _finish_record(path: str, record: _Record, snippets: list[Snippet], problems: list[str]) -> None:
    fields = record.fields
    code_field = fields.get("code")
    if record.model not in CODE_MODELS or code_field is None:
        return
    source_findings: list[tuple[int, str, str, str]] = []
    code_path = path
    if "file" in code_field.attrs:
        loaded = _code_from_file(path, code_field, problems)
        if loaded is None:
            return
        code_path, code = loaded
        first_line = 1
    elif "eval" in code_field.attrs:
        code = _value(code_field)
        if not isinstance(code, str):
            return  # computed in XML; not knowable statically
        first_line = code_field.start_line
    else:
        code = "".join(code_field.parts)
        first_line = code_field.text_line or code_field.start_line
        if code_field.child_element_line and code_field.attrs.get("type") not in ("xml", "html"):
            source_findings.append((code_field.child_element_line, "E003", "error",
                                    "child element inside <field name=\"code\">: Odoo's import_xml.rng allows only "
                                    "text here, so the module fails to install"))
        elif code_field.truncated_at and not _tail_suppressed(code_field):
            source_findings.append((code_field.truncated_at, "W100", "warning",
                                    "Odoo keeps only the text before the first XML comment inside "
                                    "<field name=\"code\">; the code after it is silently dropped"))
    if not code.strip() and not source_findings:
        return
    state = _value(fields.get("state"))
    parent_model = record.parent[0].model if record.parent else None
    if record.model == "ir.cron":
        caller = "cron"
        runs = state is None or state is _UNKNOWN or state == "code"  # ir.cron defaults state to 'code'
    else:
        caller = ("automation" if record.model == "base.automation" or parent_model == "base.automation"
                  or "base_automation_id" in fields else "server_action")
        # ir.actions.server: 17/18 default to 'object_write', 19 has no default; only 'code' runs code
        runs = state is _UNKNOWN or state == "code" or (state is None and record.model == "base.automation")
    snippets.append(Snippet(
        path=code_path, code=code, first_line=first_line, caller=caller, label=record.id,
        binding=_binding(fields),
        save_time_only=not runs,
        source_findings=source_findings,
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
    # Only a stable series prefix ('19.0.1.0.0'); '17.1.0.0' is more likely a module version.
    if len(parts) >= 4 and parts[0].isdigit() and int(parts[0]) >= 10 and parts[1] == "0":
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
