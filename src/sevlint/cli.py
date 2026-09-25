"""Command line interface."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

from . import __version__, catalog, config, profile as profiles
from .linter import Options, Report, lint_paths, lint_text
from .profile import CALLERS

# Same values as in .remote, which is imported only when `sevlint remote` runs (it pulls in
# urllib/xmlrpc; the Claude hook starts this module after every edit).
DEFAULT_KEY_ENV = "ODOO_API_KEY"
PROTOCOLS = ("auto", "json2", "xmlrpc")

RULES = {rule.code: rule.text for rule in catalog.RULES}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sevlint", description="Linter for Odoo server action code (safe_eval).")
    parser.add_argument("--version", action="version", version=f"sevlint {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="lint .py/.xml files or directories ('-' reads code from stdin)")
    check.add_argument("paths", nargs="+")
    check.add_argument("--odoo", help="Odoo series when no header/__manifest__.py says (default: 19.0)")
    check.add_argument("--caller", choices=CALLERS, help="context for code without one (default: server_action)")
    check.add_argument("--modules", default="", help="installed addons that extend the context, e.g. website,base_automation")
    check.add_argument("--all-py", action="store_true", help="lint .py files even without a '# sevlint:' header")
    _add_common(check)

    remote = sub.add_parser("remote", help="lint the code actions of a live database (read-only, via its API)",
                            description="Reads every server action, scheduled action and automation rule with "
                                        "Python code from a running Odoo 17.0+ (JSON-2 on 19+, XML-RPC before) and "
                                        "lints it with the database's own version, modules and fields. The API key "
                                        f"is read from ${DEFAULT_KEY_ENV} (see --api-key-env), the keyring or a "
                                        "prompt; never from the command line.")
    remote.add_argument("url", help="server URL, e.g. https://mycompany.odoo.com")
    remote.add_argument("--db", help="database name (required for XML-RPC and on multi-database servers)")
    remote.add_argument("--user", help="login of the API key's user (XML-RPC only)")
    remote.add_argument("--api-key-env", default=DEFAULT_KEY_ENV, metavar="VAR",
                        help=f"environment variable holding the API key (default: {DEFAULT_KEY_ENV})")
    remote.add_argument("--protocol", choices=PROTOCOLS, default="auto",
                        help="auto: JSON-2 on Odoo 19+, XML-RPC before")
    remote.add_argument("--odoo", help="lint against another Odoo version (upgrade check); fields are then checked "
                                       "with the bundled index instead of the database")
    remote.add_argument("--ids", default="", help="only these ir.actions.server ids, e.g. 12,40")
    remote.add_argument("--only", default="", help=f"only these callers: {','.join(CALLERS)}")
    remote.add_argument("--no-schema", action="store_true",
                        help="do not read ir.model.fields; check fields with the bundled per-version index")
    remote.add_argument("--dump", type=Path, metavar="DIR",
                        help="also write each action's code to DIR/<id>_<name>.py with a sevlint header")
    remote.add_argument("--timeout", type=float, default=30.0, help="seconds per request (default: 30)")
    remote.add_argument("--allow-http", action="store_true", help="allow plain http to a host other than localhost")
    remote.set_defaults(caller=None, modules="", all_py=False)
    _add_common(remote)

    explain = sub.add_parser("explain", help="describe a rule code")
    explain.add_argument("code", nargs="?")

    sub.add_parser("versions", help="list supported Odoo versions and their source commits")

    hook = sub.add_parser("hook", help="integration entry points")
    hook.add_argument("kind", choices=("claude",), help="claude: Claude Code PostToolUse hook (reads JSON on stdin)")
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--names", default="", help="extra names to treat as defined (enterprise/custom context)")
    parser.add_argument("--disable", default="", help="comma-separated codes to skip, e.g. W302,W303 (W* = all warnings)")
    parser.add_argument("--unsafe-policy", choices=("disable", "log", "raise", "terminate"),
                        help="Odoo 19.3+/20.0 server option --unsafe-policy (default: the version's default, log)")
    parser.add_argument("--target-python", help="fail unless running on this Python (X.Y), to match the Odoo server")
    parser.add_argument("--format", choices=("text", "json", "github", "sarif"), default="text",
                        help="sarif: SARIF 2.1.0 for GitHub code scanning and other viewers")
    parser.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    parser.add_argument("--config", type=Path, help="config file (default: nearest .sevlint.toml / pyproject.toml)")


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
        unsafe_policy=getattr(args, "unsafe_policy", None) or cfg.get("unsafe-policy"),
        target_python=getattr(args, "target_python", None) or cfg.get("target-python"),
    )


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _natural(text: str) -> list:
    """'ir.actions.server/10' after 'ir.actions.server/9'."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", text)]


def _uri(path: str) -> str:
    """A SARIF artifact URI: repository-relative (from the working directory) when possible."""
    local = Path(path)
    if local.is_absolute():
        try:
            local = local.relative_to(Path.cwd())
        except ValueError:
            return local.as_uri()
    return urllib.parse.quote(local.as_posix())


def _line_length(path: str, line: int, cache: dict) -> int | None:
    if path not in cache:
        try:
            cache[path] = Path(path).read_bytes().decode("utf-8", errors="replace").splitlines()
        except OSError:
            cache[path] = None
    lines = cache[path]
    return len(lines[line - 1]) if lines is not None and 0 < line <= len(lines) else None


def _sarif(report: Report) -> dict:
    rules = catalog.RULES
    index = {rule.code: i for i, rule in enumerate(rules)}
    precision = {"save": "very-high", "install": "very-high", "future": "very-high", "runtime": "high"}
    cache: dict = {}
    results = []
    for f in sorted(report.findings, key=lambda f: (_natural(f.path), f.line, f.code)):
        width = _line_length(f.path, f.line, cache)
        region = {"startLine": max(f.line, 1), "startColumn": 1, "endLine": max(f.line, 1),
                  "endColumn": (width or 0) + 1}
        where = f"{f.odoo_version} {f.caller}" + (f" {f.label}" if f.label else "")
        results.append({
            "ruleId": f.code, "ruleIndex": index[f.code], "level": "error" if f.severity == "error" else "warning",
            "message": {"text": f"{f.message} [{where}]"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": _uri(f.path)}, "region": region}}],
            "properties": {"odooVersion": f.odoo_version, "caller": f.caller},
        })
    notifications = [{"level": "error", "message": {"text": p}} for p in report.problems]
    notifications += [{"level": "note", "message": {"text": n}} for n in report.notes]
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "sevlint", "semanticVersion": __version__, "informationUri": catalog.REPO,
                "rules": [{
                    "id": rule.code, "name": rule.name,
                    "shortDescription": {"text": rule.title},
                    "fullDescription": {"text": rule.text[:1024]},
                    "help": {"text": f"{rule.text}\n\nBad:\n{rule.bad}\nGood:\n{rule.good}",
                             "markdown": catalog.explain(rule).split("\n", 1)[1].strip()},
                    "helpUri": rule.help_uri,
                    "defaultConfiguration": {"level": rule.severity},
                    "properties": {"tags": ["odoo", "safe_eval", rule.stage],
                                   "precision": precision.get(rule.stage, "medium"),
                                   "problem.severity": "error" if rule.severity == "error" else "warning"},
                } for rule in rules],
            }},
            "invocations": [{"executionSuccessful": not report.problems,
                             "toolExecutionNotifications": notifications}],
            "results": results,
        }],
    }


def render(report: Report, fmt: str) -> str:
    if fmt == "sarif":
        return json.dumps(_sarif(report), indent=1)
    if fmt == "json":
        return json.dumps({
            "findings": [f.__dict__ for f in report.findings],
            "problems": report.problems,
            "notes": report.notes,
            "summary": {"errors": report.errors, "warnings": report.warnings,
                        "snippets": report.snippets, "files": report.files},
        }, indent=1)
    lines = []
    for f in sorted(report.findings, key=lambda f: (_natural(f.path), f.line, f.code)):
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
            notes.append(f"warning: Odoo {version} supports Python {prof.python_range}; verdicts computed on "
                         f"{running} may differ")
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


def _ids(value: str) -> list[int]:
    try:
        return sorted({int(v) for v in _csv(value)})
    except ValueError:
        raise ValueError(f"--ids takes comma-separated record ids, not {value!r}") from None


def cmd_remote(args: argparse.Namespace) -> int:
    from . import remote

    only = _csv(args.only)
    if only - set(CALLERS):
        print(f"sevlint: --only takes {', '.join(CALLERS)}", file=sys.stderr)
        return 2
    transport = None

    def redact(text: str) -> str:
        return transport.redact(text) if transport is not None else text

    try:
        ids = _ids(args.ids)
        found = args.config or config.find(Path.cwd() / "-")
        opts = _checked_options(args, config.load(found) if found is not None else {})
        base = remote.parse_url(args.url, args.allow_http)
        transport = remote.Transport(base, timeout=args.timeout)
        info = remote.server_version(transport)
        version = profiles.normalize_version(args.odoo) if args.odoo else info.series
        profiles.load(version)  # an unsupported database or --odoo fails before asking for the key
        key = remote.api_key(args.api_key_env, transport.host)
        client = remote.connect(transport, info, protocol=args.protocol, db=args.db, login=args.user, key=key)
        snapshot = remote.fetch(client, ids or None)
        if only:
            snapshot.actions = [a for a in snapshot.actions if a.caller in only]
        schema = None
        if not args.no_schema and version == info.series:
            schema = remote.fetch_schema(client, remote.models_used(snapshot.actions))
        report = remote.lint(snapshot, version, opts, schema)
        written = remote.dump(snapshot, version, args.dump) if args.dump else []
    except (remote.RemoteError, config.ConfigError, OSError, ValueError) as err:
        print(f"sevlint: {redact(str(err))}", file=sys.stderr)
        return 2
    except Exception as err:  # noqa: BLE001 - a hostile or broken server must not produce a traceback
        print(f"sevlint: internal error {type(err).__name__}: {redact(str(err))}; please report it", file=sys.stderr)
        return 2
    edition = "Enterprise" if info.enterprise else "Community"
    db = f" db {args.db}" if args.db else ""
    report.notes.insert(0, f"{transport.host}{db}: Odoo {info.version} ({edition}), {len(snapshot.actions)} code "
                           f"action(s) read via {client.protocol}")
    if version != info.series:
        report.notes.append(f"linted as Odoo {version} (the database runs {info.series}); fields checked with the "
                            f"bundled index")
    elif schema is None:
        report.notes.append("fields checked with the bundled index (--no-schema)")
    if written:
        report.notes.append(f"wrote {len(written)} file(s) to {args.dump}")
    output = redact(render(report, args.format))  # labels and messages quote what the server sent
    if output:
        print(output)
    running = "%d.%d" % sys.version_info[:2]
    target = args.target_python or opts.target_python
    wrong = target if target and target != running else None
    for line in report.problems + report.notes + _python_notes(report, wrong):
        print(f"sevlint: {redact(line)}", file=sys.stderr)
    if args.format == "text":
        print(f"sevlint: {report.errors} error(s), {report.warnings} warning(s) in {report.snippets} action(s)",
              file=sys.stderr)
    if wrong:
        return 2
    if report.errors or (args.strict and report.warnings) or report.problems:
        return 1
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    if args.code:
        rule = catalog.BY_CODE.get(args.code.upper())
        if rule is None:
            print(f"unknown code {args.code}", file=sys.stderr)
            return 2
        print(catalog.explain(rule))
    else:
        for rule in catalog.RULES:
            print(f"{rule.code}  {rule.name:<26} {rule.title}")
        print(f"\n`sevlint explain CODE` shows the details and examples; all rules: {catalog.REPO}/blob/main/docs/rules.md")
    return 0


def cmd_versions(_: argparse.Namespace) -> int:
    running = "%d.%d" % sys.version_info[:2]
    for version in profiles.available_versions():
        prof = profiles.load(version)
        mark = "" if prof.python_supported else f"  (running {running} is outside this range)"
        sandbox = f"  sandbox (unsafe_policy default: {prof.sandbox_policy})" if prof.sandbox_policy else ""
        print(f"{version:<10} odoo/odoo@{prof.source_commit[:12]}  python {prof.python_range}{sandbox}{mark}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:  # a Windows console or pipe (cp1252) cannot encode every action name or path
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    args = _build_parser().parse_args(argv)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "explain":
        return cmd_explain(args)
    if args.command == "versions":
        return cmd_versions(args)
    if args.command == "remote":
        return cmd_remote(args)
    if args.command == "hook":
        from .hook import claude_post_tool_use
        return claude_post_tool_use(sys.stdin, sys.stderr)
    return 2
