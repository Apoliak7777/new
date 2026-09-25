"""Command line interface."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, config, profile as profiles
from .linter import Options, Report, lint_paths, lint_text
from .profile import CALLERS

RULES = {
    "E001": "Syntax error (or code too long/deep for the compiler). Odoo compiles `code.strip()` in exec "
            "mode: strip() removes only the first line's indentation, so an indented block is an "
            "IndentationError. Rejected when saving.",
    "E003": "XML: child element inside <field name=\"code\">. Odoo's import_xml.rng allows only text there, "
            "so the module fails to install.",
    "E101": "Forbidden opcode. The construct compiles to bytecode outside Odoo's _SAFE_OPCODES "
            "(import, `obj.attr = x`, `del d[k]`, assert, with, class, closures, a, *b = ...). "
            "Depends on the Python version Odoo runs on. Rejected when saving.",
    "E102": "Forbidden name. Any name/attribute containing '__' or listed in _UNSAFE_ATTRIBUTES "
            "(f_globals, mro, gi_frame, ...). String literals are NOT affected. Rejected when saving.",
    "E201": "Undefined name. Not in the eval context, safe_eval builtins, or assigned in the code. "
            "Odoo does not check this on save; the action raises NameError when the line runs. "
            "Common cases: type, getattr, hasattr, print, ValueError, KeyError.",
    "E202": "Attribute not exposed by a wrapped module (datetime, dateutil, time). "
            "AttributeError at runtime, e.g. time.mktime or dateutil.easter.",
    "W100": "XML: text after a comment or child element inside <field name=\"code\"> is dropped by Odoo "
            "(it stores node.text only).",
    "W210": "Name provided only by an addon (json: base_automation/website, request: website, "
            "payload: base_automation + an HTTP request, never in scheduled runs). Declare installed modules "
            "with --modules or config. `request` in a scheduled action is an unbound proxy.",
    "W301": "env.cr.commit()/rollback() inside a server action: breaks atomicity of the action. "
            "Commits inside a loop of a scheduled action (batching) are not reported.",
    "W302": "ORM query method (search, search_count, read_group, ...) inside a loop, a per-record lambda "
            "(filtered/mapped/sorted) or a helper called from one: one query per iteration. "
            "`search(..., limit=N)` in a while loop (batching) is not reported.",
    "W303": "raise UserError after write/create/unlink on the same path: the exception rolls the transaction "
            "back. Fine for an intentional dry run (disable with `# sevlint: disable=W303`).",
    "W304": "record/records in a scheduled action (ir.cron): both are None there.",
    "W305": "`record` without `records` in an action offered in list views (or kanban views on 19.0+): "
            "the code runs once, `record` is the first selected record, the rest is ignored.",
    "W306": "raise Exception(...): safe_eval re-raises it as ValueError, the user sees a server error "
            "with traceback. Raise UserError for a message.",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sevlint", description="Linter for Odoo server action code (safe_eval).")
    parser.add_argument("--version", action="version", version=f"sevlint {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="lint .py/.xml files or directories ('-' reads code from stdin)")
    check.add_argument("paths", nargs="+")
    check.add_argument("--odoo", help="Odoo series when no header/__manifest__.py says (default: 19.0)")
    check.add_argument("--caller", choices=CALLERS, help="context for code without one (default: server_action)")
    check.add_argument("--modules", default="", help="installed addons that extend the context, e.g. website,base_automation")
    check.add_argument("--names", default="", help="extra names to treat as defined (enterprise/custom context)")
    check.add_argument("--disable", default="", help="comma-separated codes to skip, e.g. W302,W303 (W* = all warnings)")
    check.add_argument("--all-py", action="store_true", help="lint .py files even without a '# sevlint:' header")
    check.add_argument("--target-python", help="fail unless running on this Python (X.Y), to match the Odoo server")
    check.add_argument("--format", choices=("text", "json", "github"), default="text")
    check.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    check.add_argument("--config", type=Path, help="config file (default: nearest .sevlint.toml / pyproject.toml)")

    explain = sub.add_parser("explain", help="describe a rule code")
    explain.add_argument("code", nargs="?")

    sub.add_parser("versions", help="list supported Odoo versions and their source commits")

    hook = sub.add_parser("hook", help="integration entry points")
    hook.add_argument("kind", choices=("claude",), help="claude: Claude Code PostToolUse hook (reads JSON on stdin)")
    return parser


def _csv(value: str) -> frozenset[str]:
    return frozenset(v.strip() for v in value.split(",") if v.strip())


def options_from(args: argparse.Namespace, cfg: dict) -> Options:
    return Options(
        odoo=profiles.normalize_version(args.odoo or cfg["odoo"]) if (args.odoo or cfg.get("odoo")) else None,
        caller=args.caller or cfg.get("caller"),
        modules=_csv(args.modules) | frozenset(cfg.get("modules", [])),
        names=_csv(args.names) | frozenset(cfg.get("names", [])),
        disabled=_csv(args.disable) | frozenset(cfg.get("disable", [])),
        all_py=args.all_py,
    )


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def render(report: Report, fmt: str) -> str:
    if fmt == "json":
        return json.dumps({
            "findings": [f.__dict__ for f in report.findings],
            "problems": report.problems,
            "notes": report.notes,
            "summary": {"errors": report.errors, "warnings": report.warnings,
                        "snippets": report.snippets, "files": report.files},
        }, indent=1)
    lines = []
    for f in sorted(report.findings, key=lambda f: (f.path, f.line, f.code)):
        where = f"{f.odoo_version} {f.caller}" + (f" {f.label}" if f.label else "")
        if fmt == "github":
            level = "error" if f.severity == "error" else "warning"
            lines.append(f"::{level} file={_escape_property(f.path)},line={f.line},"
                         f"title={_escape_property('sevlint ' + f.code)}::"
                         f"{_escape_data(f'{f.code} {f.message} [{where}]')}")
        else:
            lines.append(f"{f.path}:{f.line}: {f.code} {f.message} [{where}]")
    return "\n".join(lines)


def _python_notes(report: Report, target: str | None) -> list[str]:
    notes = []
    running = "%d.%d" % sys.version_info[:2]
    if target and target != running:
        notes.append(f"error: target-python {target} but running {running}; "
                     f"run e.g. `uvx --python {target} sevlint ...` (opcodes differ between Python versions)")
    for version in sorted(report.versions):
        prof = profiles.load(version)
        if not prof.python_supported:
            lo, hi = ".".join(map(str, prof.python_min)), ".".join(map(str, prof.python_max))
            notes.append(f"warning: Odoo {version} supports Python {lo}-{hi}; verdicts computed on {running} may differ")
    return notes


class _Configs:
    """Nearest config for each linted file (like pre-commit and the Claude hook), loaded once."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.loaded: dict[Path | None, dict] = {}
        self.options: dict[Path | None, Options] = {}

    def config_for(self, path: Path) -> Path | None:
        return self.args.config or config.find(path)

    def options_for(self, path: Path) -> Options:
        found = self.config_for(path.absolute())
        if found not in self.options:
            cfg = config.load(found) if found is not None else {}
            self.loaded[found] = cfg
            self.options[found] = _checked_options(self.args, cfg)
        return self.options[found]

    @property
    def targets(self) -> set[str]:
        return {cfg["target-python"] for cfg in self.loaded.values() if cfg.get("target-python")}


def _read_stdin() -> str:
    # Bytes, decoded as UTF-8: on Windows a piped stdin would otherwise be decoded as cp1252.
    return sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")


def cmd_check(args: argparse.Namespace) -> int:
    configs = _Configs(args)
    if "-" in args.paths and len(args.paths) > 1:
        print("sevlint: '-' (stdin) cannot be combined with paths", file=sys.stderr)
        return 2
    try:
        if args.odoo:
            profiles.load(args.odoo)  # fail fast on a bad --odoo
        if args.paths == ["-"]:
            report = lint_text(_read_stdin(), "<stdin>", configs.options_for(Path.cwd() / "-"))
        else:
            report = lint_paths(args.paths, Options(), options_for=configs.options_for)
    except (config.ConfigError, OSError, ValueError) as err:
        print(f"sevlint: {err}", file=sys.stderr)
        return 2
    output = render(report, args.format)
    if output:
        print(output)
    running = "%d.%d" % sys.version_info[:2]
    targets = {args.target_python} if args.target_python else configs.targets
    wrong = sorted(t for t in targets if t != running)
    notes = _python_notes(report, wrong[0] if wrong else None)
    if len(wrong) > 1:
        notes.append(f"error: the linted paths need different Pythons ({', '.join(sorted(targets))}); run them separately")
    for line in report.problems + report.notes + notes:
        print(f"sevlint: {line}", file=sys.stderr)
    if args.format == "text":
        print(f"sevlint: {report.errors} error(s), {report.warnings} warning(s) in {report.snippets} snippet(s) "
              f"from {report.files} file(s)", file=sys.stderr)
    if wrong:
        return 2
    if report.errors or (args.strict and report.warnings) or report.problems:
        return 1
    return 0


def _checked_options(args: argparse.Namespace, cfg: dict) -> Options:
    opts = options_from(args, cfg)
    if opts.odoo:
        profiles.load(opts.odoo)  # ValueError -> exit 2 for a bad config value
    return opts


def cmd_explain(args: argparse.Namespace) -> int:
    if args.code:
        text = RULES.get(args.code.upper())
        if text is None:
            print(f"unknown code {args.code}", file=sys.stderr)
            return 2
        print(f"{args.code.upper()}: {text}")
    else:
        for code, text in RULES.items():
            print(f"{code}: {text}")
    return 0


def cmd_versions(_: argparse.Namespace) -> int:
    running = "%d.%d" % sys.version_info[:2]
    for version in profiles.available_versions():
        prof = profiles.load(version)
        lo, hi = ".".join(map(str, prof.python_min)), ".".join(map(str, prof.python_max))
        mark = "" if prof.python_supported else f"  (running {running} is outside this range)"
        print(f"{version}  odoo/odoo@{prof.source_commit[:12]}  python {lo}-{hi}{mark}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "explain":
        return cmd_explain(args)
    if args.command == "versions":
        return cmd_versions(args)
    if args.command == "hook":
        from .hook import claude_post_tool_use
        return claude_post_tool_use(sys.stdin, sys.stderr)
    return 2
