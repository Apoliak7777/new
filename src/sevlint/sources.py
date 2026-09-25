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
    """``# sevlint: odoo=19.0 caller=cron modules=website names=foo,bar disable=W302 binding=list,form``"""
    header: Header | None = None
    for line in text.splitlines()[:HEADER_SCAN_LINES]:
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


def read_xml(path: str, data: bytes) -> tuple[list[Snippet], list[str]]:
    if not data.strip():
        return [], []
    parser = expat.ParserCreate()
    snippets: list[Snippet] = []
    record: dict | None = None
    field_name: str | None = None
    depth_in_field = 0

    def start(tag, attrs):
        nonlocal record, field_name, depth_in_field
        if field_name is not None:
            depth_in_field += 1
            return
        if tag == "record":
            record = {"model": attrs.get("model"), "id": attrs.get("id", ""), "fields": {}, "code_line": None,
                      "line": parser.CurrentLineNumber}
        elif tag == "field" and record is not None:
            field_name = attrs.get("name")
            depth_in_field = 0
            record["fields"].setdefault(field_name, {"text": [], "attrs": attrs, "line": None})

    def end(tag):
        nonlocal record, field_name, depth_in_field
        if field_name is not None:
            if depth_in_field:
                depth_in_field -= 1
                return
            if tag == "field":
                field_name = None
                return
        if tag == "record" and record is not None:
            _finish_record(path, record, snippets)
            record = None

    def chars(text):
        if record is not None and field_name is not None:
            entry = record["fields"][field_name]
            if entry["line"] is None:
                entry["line"] = parser.CurrentLineNumber
            entry["text"].append(text)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    try:
        parser.Parse(data, True)
    except expat.ExpatError as err:
        return [], [f"{path}: XML parse error: {err}"]
    return snippets, []


def _finish_record(path: str, record: dict, snippets: list[Snippet]) -> None:
    fields = record["fields"]
    code = fields.get("code")
    if record["model"] not in CODE_MODELS or code is None or code["line"] is None:
        return
    state = "".join(fields["state"]["text"]).strip() if "state" in fields else None
    if state is not None and state != "code":
        return
    if record["model"] == "ir.cron":
        caller = "cron"
    elif record["model"] == "base.automation" or "base_automation_id" in fields:
        caller = "automation"
    else:
        caller = "server_action"
    binding = None
    if "binding_model_id" in fields:
        view_types = "".join(fields["binding_view_types"]["text"]).strip() if "binding_view_types" in fields else ""
        binding = view_types or "list,form"  # Odoo's default binding_view_types
    snippets.append(Snippet(path=path, code="".join(code["text"]), first_line=code["line"],
                            caller=caller, label=record["id"], binding=binding))


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
