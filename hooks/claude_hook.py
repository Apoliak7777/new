"""Claude Code plugin hook entry point: runs sevlint from the plugin directory, nothing to install."""
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.stderr.write("sevlint: the hook needs Python 3.10+ (running %d.%d); set SEVLINT_PYTHON\n" % sys.version_info[:2])
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sevlint.hook import claude_post_tool_use  # noqa: E402

sys.exit(claude_post_tool_use(sys.stdin, sys.stderr))
