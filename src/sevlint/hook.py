"""Claude Code PostToolUse hook: lint the file Claude just wrote and feed problems back.

Exit 0 = nothing to say. Exit 2 = stderr is shown to Claude (the tool already ran).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, profile as profiles
from .cli import options_from, render
from .linter import lint_paths

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


def _emit(stderr, lines: list[str], path: Path) -> int:
    body, used = [], 0
    for line in lines:
        if used + len(line) > MAX_OUTPUT:
            body.append(f"... {len(lines) - len(body)} more; run `sevlint check {path}` for the full list")
            break
        body.append(line)
        used += len(line) + 1
    stderr.write("sevlint found problems in Odoo server action code "
                 "(E = Odoo rejects it or it crashes, W = likely bug):\n")
    stderr.write("\n".join(body) + "\n")
    stderr.write("Fix the errors; explain any warning you keep. `sevlint explain <CODE>` describes a rule.\n")
    return BLOCKING_EXIT


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
    cfg: dict = {}
    cfg_path = config.find(path)
    if cfg_path is not None:
        try:
            cfg = config.load(cfg_path)
        except (config.ConfigError, OSError) as err:
            stderr.write(f"sevlint: cannot use the project config, fix it: {err}\n")
            return BLOCKING_EXIT
    no_flags = argparse.Namespace(odoo=None, caller=None, modules="", names="", disable="", all_py=False)
    try:
        report = lint_paths([str(path)], options_from(no_flags, cfg))
    except ValueError as err:
        stderr.write(f"sevlint: {err}\n")
        return BLOCKING_EXIT
    if not report.findings and not report.problems:
        return 0
    lines = render(report, "text").splitlines() if report.findings else []
    lines += [f"sevlint: {p}" for p in report.problems]
    python_problem = _python_problem(report.versions, cfg.get("target-python"))
    if python_problem:
        lines.insert(0, f"sevlint: {python_problem}")
    return _emit(stderr, lines, path)
