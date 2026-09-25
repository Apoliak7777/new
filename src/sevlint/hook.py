"""Claude Code PostToolUse hook: lint the file Claude just wrote and feed problems back."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from . import config
from .cli import options_from, render
from .linter import lint_paths

BLOCKING_EXIT = 2  # PostToolUse: stderr is shown to Claude
MAX_OUTPUT = 9000  # Claude Code caps hook output at 10,000 characters


def claude_post_tool_use(stdin: TextIO, stderr: TextIO) -> int:
    try:
        event = json.load(stdin)
    except json.JSONDecodeError:
        return 0  # never break the session on unexpected input
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0
    path = Path(file_path)
    if not path.is_absolute() and event.get("cwd"):
        path = Path(event["cwd"]) / path
    if path.suffix not in (".py", ".xml") or not path.is_file():
        return 0
    cfg: dict = {}
    cfg_path = config.find(path)
    if cfg_path is not None:
        try:
            cfg = config.load(cfg_path)
        except (config.ConfigError, OSError):
            cfg = {}
    no_flags = argparse.Namespace(odoo=None, caller=None, modules="", names="", disable="", all_py=False)
    opts = options_from(no_flags, cfg)
    try:
        report = lint_paths([str(path)], opts)
    except ValueError as err:
        stderr.write(f"sevlint: {err}\n")
        return 0
    if not report.findings:
        return 0
    lines = render(report, "text").splitlines()
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
