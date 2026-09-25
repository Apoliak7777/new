"""Glue: snippets in, findings out."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import engine, profile as profiles, rules, sources

INLINE_DISABLE_RE = re.compile(r"#\s*sevlint:\s*disable(?:=(?P<codes>[\w,]+))?")
DEFAULT_VERSION = "19.0"


@dataclass(frozen=True)
class Options:
    odoo: str | None = None  # used when neither header nor manifest says otherwise
    caller: str | None = None
    modules: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    disabled: frozenset[str] = frozenset()
    all_py: bool = False


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    code: str
    severity: str
    message: str
    odoo_version: str
    caller: str
    label: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # input problems (bad header, XML errors)
    snippets: int = 0
    files: int = 0
    versions: set[str] = field(default_factory=set)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


def _suppressed(line_text: str, code: str) -> bool:
    match = INLINE_DISABLE_RE.search(line_text)
    if not match:
        return False
    codes = match.group("codes")
    return codes is None or code in codes.split(",")


def lint_code(code: str, version: str, caller: str = "server_action", *,
              modules: frozenset[str] = frozenset(), names: frozenset[str] = frozenset(),
              disabled: frozenset[str] = frozenset(), binding: str | None = None) -> list[engine.Diagnostic]:
    """Lint one piece of server action code; lines are relative to ``code``.

    ``binding`` is the action's binding_view_types when it is offered in the Action menu
    (e.g. "list,form"); None when unknown or not bound.
    """
    prof = profiles.load(version)
    analysis = engine.analyse(code)
    diags = list(analysis.diagnostics)
    diags += engine.check_save_time(analysis, prof)
    diags += engine.check_names(analysis, prof, modules, names)
    if analysis.tree is not None:
        defined = engine.defined_toplevel_names(analysis.code)
        list_bound = bool(binding) and "list" in binding.split(",")
        diags += rules.run_rules(analysis.tree, caller, defined, list_bound=list_bound)
    raw_lines = code.splitlines()
    out = []
    for diag in sorted(set(diags)):
        diag = diag.shifted(analysis.line_offset)
        if diag.code in disabled or diag.code[0] + "*" in disabled:
            continue
        text = raw_lines[diag.line - 1] if 0 < diag.line <= len(raw_lines) else ""
        if _suppressed(text, diag.code):
            continue
        out.append(diag)
    return out


def lint_snippet(snippet: sources.Snippet, opts: Options, fallback_version: str) -> list[Finding]:
    version = snippet.odoo_version or fallback_version
    caller = snippet.caller or opts.caller or "server_action"
    diags = lint_code(snippet.code, version, caller,
                      modules=opts.modules | snippet.modules,
                      names=opts.names | snippet.names,
                      disabled=opts.disabled | snippet.disabled,
                      binding=snippet.binding)
    return [Finding(snippet.path, snippet.first_line + d.line - 1, d.code, d.severity, d.message,
                    version, caller, snippet.label) for d in diags]


def collect_files(paths: list[str]) -> list[tuple[Path, bool]]:
    """(file, explicitly_given) pairs; directories are walked for .py/.xml."""
    out: list[tuple[Path, bool]] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.suffix in (".py", ".xml") and child.is_file() \
                        and not any(part.startswith(".") for part in child.relative_to(path).parts):
                    out.append((child, False))
        else:
            out.append((path, True))
    return out


def lint_paths(paths: list[str], opts: Options) -> Report:
    report = Report()
    for path, explicit in collect_files(paths):
        if not path.is_file():
            report.problems.append(f"{path}: no such file")
            continue
        if path.suffix == ".xml":
            snippets, problems = sources.read_xml(str(path), path.read_bytes())
        elif path.suffix == ".py":
            text = path.read_text(encoding="utf-8", errors="replace")
            snippets, problems = sources.read_python(str(path), text, require_header=not opts.all_py)
        else:
            if explicit:
                report.problems.append(f"{path}: skipped (only .py and .xml are supported)")
            continue
        report.problems += [f"{path}: {p}" if not p.startswith(str(path)) else p for p in problems]
        if not snippets:
            continue
        report.files += 1
        resolved = path.resolve()
        fallback = sources.manifest_version(resolved) or opts.odoo or DEFAULT_VERSION
        installed = sources.manifest_modules(resolved)
        for snippet in snippets:
            snippet.modules |= installed
            report.snippets += 1
            report.versions.add(snippet.odoo_version or fallback)
            report.findings += lint_snippet(snippet, opts, fallback)
    return report


def lint_text(text: str, path: str, opts: Options) -> Report:
    """Lint code given directly (stdin); the header is optional."""
    report = Report(files=1)
    snippets, problems = sources.read_python(path, text, require_header=False)
    report.problems += problems
    fallback = opts.odoo or DEFAULT_VERSION
    for snippet in snippets:
        report.snippets += 1
        report.versions.add(snippet.odoo_version or fallback)
        report.findings += lint_snippet(snippet, opts, fallback)
    return report
