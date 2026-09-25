#!/usr/bin/env python3
"""Regenerate docs/rules.md from src/sevlint/catalog.py (tests/test_catalog.py checks it is current)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from sevlint import catalog  # noqa: E402

(ROOT / "docs" / "rules.md").write_text(catalog.markdown(), encoding="utf-8", newline="\n")
print("docs/rules.md written", file=sys.stderr)
