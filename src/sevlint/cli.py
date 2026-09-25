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
    "E001": "Syntax error. Odoo compiles `code.strip()` in exec mode, so an indented first line "
            "or a stray indent is an IndentationError. Rejected when saving.",
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
    "W210": "Name provided only by an addon (json: base_automation/website, request: website, "
            "payload: base_automation webhooks). Declare installed modules with --modules or config.",
    "W301": "env.cr.commit()/rollback() inside a server action: breaks atomicity of the action.",
    "W302": "ORM query method (search, search_count, read_group, ...) inside a loop: one query per iteration.",
    "W303": "raise UserError after write/create/unlink: the exception rolls the transaction back. "
            "Fine for an intentional dry run (disable with `# sevlint: disable=W303`).",
    "W304": "record/records in a scheduled action (ir.cron): both are None there.",
    "W305": "`record` without `records` in an action offered in list views (binding_view_types contains "
            "'list'): the code runs once, `record` is the first selected record, the rest is ignored.",
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


def render(report: Report, fmt: str) -> str:
    if fmt == "json":
        return json.dumps({
            "findings": [f.__dict__ for f in report.findings],
            "problems": report.problems,
            "summary": {"errors": report.errors, "warnings": report.warnings,
                        "snippets": report.snippets, "files": report.files},
        }, indent=1)
    lines = []
    for f in sorted(report.findings, key=lambda f: (f.path, f.line, f.code)):
        where = f"{f.odoo_version} {f.caller}" + (f" {f.label}" if f.label else "")
        if fmt == "github":
            level = "error" if f.severity == "error" else "warning"
            msg = f"{f.code} {f.message} [{where}]".replace("%", "%25").replace("\n", "%0A")
            lines.append(f"::{level} file={f.path},line={f.line},title=sevlint {f.code}::{msg}")
        else:
            lines.append(f"{f.path}:{f.line}: {f.code} {f.message} [{where}]")
    return "\n".join(lines)


def _python_notes(report: Report, target: str | None) -> list[str]:
    notes = []
    running = "%d.%d" % sys.version_info[:2]
    if target and target != running:
        notes.append(f"error: --target-python {target} but running {running}; "
                     f"run e.g. `uvx --python {target} sevlint ...` (opcodes differ between Python versions)")
    for version in sorted(report.versions):
        prof = profiles.load(version)
        if not prof.python_supported:
            lo, hi = ".".join(map(str, prof.python_min)), ".".join(map(str, prof.python_max))
            notes.append(f"warning: Odoo {version} supports Python {lo}-{hi}; verdicts computed on {running} may differ")
    return notes


def cmd_check(args: argparse.Namespace) -> int:
    cfg: dict = {}
    cfg_path = args.config or config.find(Path.cwd())
    if cfg_path is not None:
        try:
            cfg = config.load(cfg_path)
        except (config.ConfigError, OSError) as err:
            print(f"sevlint: {err}", file=sys.stderr)
            return 2
    opts = options_from(args, cfg)
    try:
        if args.paths == ["-"]:
            report = lint_text(sys.stdin.read(), "<stdin>", opts)
        else:
            report = lint_paths(args.paths, opts)
    except ValueError as err:  # unknown Odoo version
        print(f"sevlint: {err}", file=sys.stderr)
        return 2
    output = render(report, args.format)
    if output:
        print(output)
    target = args.target_python or cfg.get("target-python")
    notes = _python_notes(report, target)
    for line in report.problems + notes:
        print(f"sevlint: {line}", file=sys.stderr)
    if args.format == "text":
        print(f"sevlint: {report.errors} error(s), {report.warnings} warning(s) in {report.snippets} snippet(s) "
              f"from {report.files} file(s)", file=sys.stderr)
    if target and target != "%d.%d" % sys.version_info[:2]:
        return 2
    if report.errors or (args.strict and report.warnings) or report.problems:
        return 1
    return 0


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
