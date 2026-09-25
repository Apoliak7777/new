"""Claude Code plugin hook entry point: runs sevlint from the plugin directory, nothing to install."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sevlint.hook import claude_post_tool_use  # noqa: E402

sys.exit(claude_post_tool_use(sys.stdin, sys.stderr))
