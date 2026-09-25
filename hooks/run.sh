#!/bin/sh
# Claude Code hook launcher: find a Python >= 3.10 and run sevlint from this plugin checkout.
# Probing each candidate skips Windows' Microsoft Store "python3" alias and too-old interpreters.
# SEVLINT_PYTHON selects the interpreter (e.g. the Odoo server's Python version).
here=$(cd "$(dirname "$0")" && pwd)
usable() {
    command -v "$1" >/dev/null 2>&1 &&
        "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' </dev/null >/dev/null 2>&1
}
if [ -n "${SEVLINT_PYTHON:-}" ]; then
    if usable "$SEVLINT_PYTHON"; then
        exec "$SEVLINT_PYTHON" "$here/claude_hook.py"
    fi
    echo "sevlint: SEVLINT_PYTHON=$SEVLINT_PYTHON is not a Python >= 3.10; the hook did not run" >&2
    exit 1
fi
for py in python3 python py; do
    if usable "$py"; then
        exec "$py" "$here/claude_hook.py"
    fi
done
echo "sevlint: no Python >= 3.10 found (tried python3, python, py); set SEVLINT_PYTHON" >&2
exit 1
