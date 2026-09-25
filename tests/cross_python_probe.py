"""Run by tests/test_cross_python.py under each interpreter: Odoo's verdict and sevlint's
cross-Python prediction for every snippet of the corpus, as JSON on stdout."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "src")]

import oracle  # noqa: E402
from corpus import CROSS_SNIPPETS, SNIPPETS  # noqa: E402
from sevlint import crosspy, engine, profile  # noqa: E402

VERSION = "19.0"
prof = profile.load(VERSION)
result = {"running": "%d.%d" % sys.version_info[:2], "snippets": {}}
for name, code in {**SNIPPETS, **CROSS_SNIPPETS}.items():
    analysis = engine.analyse(code)
    predicted = sorted({"%d.%d" % v for _, _, bad in crosspy.findings(analysis, prof) for v in bad})
    result["snippets"][name] = {"rejected": oracle.rejects_on_save(VERSION, code), "predicted": predicted}
print(json.dumps(result))
