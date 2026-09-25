#!/bin/sh
# Claude Code hook launcher: find a Python >= 3.10 and run sevlint from this plugin checkout.
# Probing each candidate skips Windows' Microsoft Store "python3" alias and too-old interpreters.
# SEVLINT_PYTHON overrides the search (e.g. the Odoo server's Python version).
here=$(cd "$(dirname "$0")" && pwd)
for py in "${SEVLINT_PYTHON:-}" python3 python py; do
    [ -n "$py" ] || continue
    command -v "$py" >/dev/null 2>&1 || continue
    if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' </dev/null >/dev/null 2>&1; then
        exec "$py" "$here/claude_hook.py"
    fi
done
echo "sevlint: no Python >= 3.10 found (tried \$SEVLINT_PYTHON, python3, python, py); the hook did not run" >&2
exit 1
