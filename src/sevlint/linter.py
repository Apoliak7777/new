"""Glue: snippets in, findings out."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import crosspy, engine, fields, profile as profiles, rules, sources

INLINE_DISABLE_RE = re.compile(r"#\s*sevlint:\s*disable(?:=(?P<codes>[\w,]+))?")
DEFAULT_VERSION = "19.0"
SAVE_TIME_CODES = ("E001", "E004", "E101", "E102")


@dataclass(frozen=True)
class Options:
    odoo: str | None = None  # used when neither header nor manifest says otherwise
    caller: str | None = None
    modules: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    disabled: frozenset[str] = frozenset()
    all_py: bool = False
    unsafe_policy: str | None = None  # 19.3+ sandbox; None: the version's default
    target_python: str | None = None  # pinned server Python: disables W110 (the verdict is exact)


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
    problems: list[str] = field(default_factory=list)  # input problems: they fail the run
    notes: list[str] = field(default_factory=list)  # informational, never change the exit code
    snippets: int = 0
    files: int = 0
    versions: set[str] = field(default_factory=set)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    def merge(self, other: "Report") -> None:
        self.findings += other.findings
        self.problems += other.problems
        self.notes += other.notes
        self.snippets += other.snippets
        self.files += other.files
        self.versions |= other.versions


def _suppressed(line_text: str, code: str) -> bool:
    match = INLINE_DISABLE_RE.search(line_text)
    if not match:
        return False
    codes = match.group("codes")
    return codes is None or code in codes.split(",")


def _list_bound(binding: str | None, version: str) -> bool:
    """Offered where several records can be selected: list views, and kanban views from 19.0."""
    if not binding:
        return False
    view_types = {v.strip() for v in binding.split(",")}
    return "list" in view_types or ("kanban" in view_types and profiles.version_key(version) >= (19, 0))


def lint_code(code: str, version: str, caller: str = "server_action", *,
              modules: frozenset[str] = frozenset(), names: frozenset[str] = frozenset(),
              disabled: frozenset[str] = frozenset(), binding: str | None = None,
              runtime_checks: bool = True, unsafe_policy: str | None = None,
              model: str | None = None, target_python: str | None = None) -> list[engine.Diagnostic]:
    """Lint one piece of server action code; lines are relative to ``code``.

    ``binding`` is the action's binding_view_types when it is offered in the Action menu
    (e.g. "list,form"); None when unknown or not bound. ``runtime_checks=False`` keeps only
    the save-time checks (Odoo validates the code of every action, whatever its state).
    """
    prof = profiles.load(version)
    analysis = engine.analyse(code)
    diags = list(analysis.diagnostics)
    try:
        diags += engine.check_save_time(analysis, prof)
        diags += engine.check_sandbox(analysis, prof, unsafe_policy)
        diags += crosspy.check_cross_python(analysis, prof, target_python)
        if runtime_checks:
            diags += engine.check_names(analysis, prof, modules, names, caller)
            if analysis.tree is not None:
                defined = engine.defined_toplevel_names(analysis.code)
                diags += rules.run_rules(analysis.tree, analysis.code, caller, defined,
                                         list_bound=_list_bound(binding, version), version=version)
                diags += fields.check_fields(analysis.tree, version, model)
    except (engine.TooComplex, RecursionError, MemoryError) as err:
        diags = [engine.Diagnostic(1, "E001", f"{type(err).__name__}: code too long or too deeply nested for "
                                              f"Python's compiler; Odoo's check fails the same way "
                                              f"({engine.SAVE_TIME})")]
    if not runtime_checks:
        diags = [d for d in diags if d.code in SAVE_TIME_CODES or d.code == "W110"]
    raw_lines = engine.split_lines(code)
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
    disabled = opts.disabled | snippet.disabled
    diags = lint_code(snippet.code, version, caller,
                      modules=opts.modules | snippet.modules,
                      names=opts.names | snippet.names,
                      disabled=disabled,
                      binding=snippet.binding,
                      runtime_checks=not snippet.save_time_only,
                      unsafe_policy=opts.unsafe_policy,
                      model=snippet.model,
                      target_python=opts.target_python)
    findings = [Finding(snippet.path, snippet.first_line + d.line - 1, d.code, d.severity, d.message,
                        version, caller, snippet.label) for d in diags]
    for line, code, severity, message in snippet.source_findings:
        if code not in disabled and code[0] + "*" not in disabled:
            findings.append(Finding(snippet.path, line, code, severity, message, version, caller, snippet.label))
    return findings


def collect_files(paths: list[str]) -> tuple[list[tuple[Path, bool]], list[str]]:
    """(file, explicitly_given) pairs and notes. Directories are walked for .py/.xml,
    following symlinks (addons paths are often symlink farms) without looping."""
    out: list[tuple[Path, bool]] = []
    notes: list[str] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_dir():
            out.append((path, True))
            continue
        seen: set[tuple[int, int]] = set()
        for root, dirs, files in os.walk(path, followlinks=True):
            try:
                st = os.stat(root)
            except OSError:
                dirs[:] = []
                continue
            if (st.st_dev, st.st_ino) in seen:
                dirs[:] = []
                continue
            seen.add((st.st_dev, st.st_ino))
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__"))
            for name in sorted(files):
                if name.endswith((".py", ".xml")):
                    out.append((Path(root) / name, False))
    return out, notes


def _read_snippets(path: Path, opts: Options) -> tuple[list[sources.Snippet], list[str]]:
    if path.suffix == ".xml":
        return sources.read_xml(str(path), path.read_bytes())
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return sources.read_python(str(path), text, require_header=not opts.all_py)


def lint_paths(paths: list[str], opts: Options, options_for=None) -> Report:
    """Lint files and directories. ``options_for(path)`` may supply per-file options
    (e.g. from the nearest config file); ``opts`` is used otherwise."""
    report = Report()
    files, report.notes = collect_files(paths)
    for path, explicit in files:
        if explicit and not path.exists():
            report.problems.append(f"{path}: no such file or directory")
            continue
        if path.suffix not in (".py", ".xml"):
            if explicit:
                report.notes.append(f"{path}: skipped (only .py and .xml are linted)")
            continue
        if not path.is_file():
            report.problems.append(f"{path}: not a regular file")
            continue
        file_opts = options_for(path) if options_for else opts
        try:
            snippets, problems = _read_snippets(path, file_opts)
        except OSError as err:
            report.problems.append(f"{path}: cannot read ({err.strerror or err})")
            continue
        report.problems += [p if p.startswith(str(path)) else f"{path}: {p}" for p in problems]
        if not snippets:
            continue
        report.files += 1
        located = path.absolute()  # not resolve(): siblings of a symlinked module live next to the link
        fallback = sources.manifest_version(located) or file_opts.odoo or DEFAULT_VERSION
        installed = sources.manifest_modules(located)
        for snippet in snippets:
            snippet.modules |= installed
            _lint_into(report, snippet, file_opts, fallback)
    return report


def _lint_into(report: Report, snippet: sources.Snippet, opts: Options, fallback: str) -> None:
    where = f"{snippet.path}:{snippet.first_line}" + (f" ({snippet.label})" if snippet.label else "")
    try:
        findings = lint_snippet(snippet, opts, fallback)
    except ValueError as err:  # unsupported Odoo version for this snippet
        report.problems.append(f"{where}: {err}")
        return
    except Exception as err:  # noqa: BLE001 - one bad snippet must not abort the run
        report.problems.append(f"{where}: internal error {type(err).__name__}: {err}; please report it")
        return
    report.snippets += 1
    report.versions.add(snippet.odoo_version or fallback)
    report.findings += findings


def lint_text(text: str, path: str, opts: Options) -> Report:
    """Lint code given directly (stdin); the header is optional."""
    report = Report(files=1)
    snippets, problems = sources.read_python(path, text.lstrip("﻿"), require_header=False)
    report.problems += problems
    for snippet in snippets:
        _lint_into(report, snippet, opts, opts.odoo or DEFAULT_VERSION)
    return report
