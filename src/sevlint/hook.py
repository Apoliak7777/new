"""Claude Code PostToolUse hook: lint the file Claude just wrote and feed problems back.

Exit 0 = nothing to say. Exit 2 = stderr is shown to Claude (the tool already ran).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, profile as profiles
from .cli import RULES, options_from, render
from .linter import Options, lint_paths

BLOCKING_EXIT = 2
MAX_OUTPUT = 9000  # Claude Code caps hook output at 10,000 characters


def _read_event(stdin) -> dict | None:
    # Bytes, not text: on Windows a piped stdin is decoded as cp1252 and Claude Code sends UTF-8.
    raw = stdin.buffer.read() if hasattr(stdin, "buffer") else stdin.read()
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return event if isinstance(event, dict) else None


def _python_problem(versions: set[str], target: str | None) -> str | None:
    running = "%d.%d" % sys.version_info[:2]
    if target and target != running:
        return (f"the hook runs on Python {running} but the project's target-python is {target}; set SEVLINT_PYTHON "
                f"to a Python {target} interpreter")
    for version in sorted(versions):
        prof = profiles.load(version)
        if not prof.python_supported:
            lo, hi = ".".join(map(str, prof.python_min)), ".".join(map(str, prof.python_max))
            return (f"the hook runs on Python {running}, outside Odoo {version}'s {lo}-{hi}; verdicts may be wrong "
                    f"(set SEVLINT_PYTHON)")
    return None


def _emit(stderr, lines: list[str], codes: list[str]) -> int:
    body, used = [], 0
    for line in lines:
        if used + len(line) > MAX_OUTPUT:
            body.append(f"... and {len(lines) - len(body)} more")
            break
        body.append(line)
        used += len(line) + 1
    stderr.write("sevlint found problems in Odoo server action code "
                 "(E = Odoo rejects it or it crashes, W = likely bug):\n")
    stderr.write("\n".join(body) + "\n")
    explained = [f"  {code}: {RULES[code]}" for code in codes if code in RULES]
    if explained and used + sum(map(len, explained)) < MAX_OUTPUT:
        stderr.write("Rules:\n" + "\n".join(explained) + "\n")
    stderr.write("Fix the errors; explain any warning you keep "
                 "(or silence it on its line with `# sevlint: disable=CODE`).\n")
    return BLOCKING_EXIT


def _looks_like_odoo_xml(path: Path) -> bool:
    try:
        head = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"<odoo" in head or b"<openerp" in head


def claude_post_tool_use(stdin, stderr) -> int:
    event = _read_event(stdin)
    if event is None:
        return 0  # never break the session on unexpected input
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(file_path, str) or not file_path:
        return 0
    path = Path(file_path)
    if not path.is_absolute() and isinstance(event.get("cwd"), str):
        path = Path(event["cwd"]) / path
    if path.suffix not in (".py", ".xml") or not path.is_file():
        return 0

    # Stay silent for files without server action code (most edits), before touching config.
    probe = lint_paths([str(path)], Options())
    parse_problems = [p for p in probe.problems if "XML" in p and _looks_like_odoo_xml(path)]
    if not probe.snippets and not parse_problems:
        return 0

    cfg: dict = {}
    notes: list[str] = []
    cfg_path = config.find(path)
    if cfg_path is not None:
        try:
            cfg = config.load(cfg_path)
        except config.ConfigError as err:
            if config.tomllib is None:  # Python 3.10 without tomli: lint without the config
                notes.append(f"sevlint: {cfg_path} ignored: {err}")
            else:
                stderr.write(f"sevlint: cannot use the project config, fix it: {err}\n")
                return BLOCKING_EXIT
        except OSError as err:
            notes.append(f"sevlint: {cfg_path} ignored: {err}")
    no_flags = argparse.Namespace(odoo=None, caller=None, modules="", names="", disable="", all_py=False)
    try:
        report = lint_paths([str(path)], options_from(no_flags, cfg))
    except ValueError:
        return 0  # e.g. an unsupported odoo version in the config: nothing Claude can fix
    # Unsupported Odoo series (<= 16.0) are not ours to judge; unparseable non-Odoo XML neither.
    problems = [p for p in report.problems if "unsupported Odoo version" not in p
                and ("XML" not in p or _looks_like_odoo_xml(path))]
    python_problem = _python_problem(report.versions, cfg.get("target-python"))
    if not report.findings and not problems:
        if python_problem:  # a clean verdict from the wrong interpreter: tell the user, not Claude
            stderr.write(f"sevlint: {python_problem}\n")
            return 1
        return 0
    lines = notes + ([f"sevlint: {python_problem}"] if python_problem else [])
    lines += render(report, "text").splitlines() if report.findings else []
    lines += [f"sevlint: {p}" for p in problems]
    codes = sorted({f.code for f in report.findings})
    return _emit(stderr, lines, codes)
