"""W110 against reality: Odoo's safe_eval run under several Pythons.

Set SEVLINT_TEST_PYTHONS to interpreters separated by os.pathsep (each with python-dateutil
and pytz installed). From every interpreter that accepts a snippet, sevlint's prediction of
which other Pythons reject it must equal what Odoo's safe_eval really does on them.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from corpus import CROSS_SNIPPETS, SNIPPETS

PYTHONS = [p for p in os.environ.get("SEVLINT_TEST_PYTHONS", "").split(os.pathsep) if p]
PROBE = Path(__file__).with_name("cross_python_probe.py")


@pytest.fixture(scope="module")
def results():
    if len(PYTHONS) < 2:
        pytest.skip("set SEVLINT_TEST_PYTHONS to at least two interpreters")
    out = {}
    for python in PYTHONS:
        data = json.loads(subprocess.run([python, str(PROBE)], check=True, capture_output=True, text=True).stdout)
        out[data["running"]] = data["snippets"]
    return out


@pytest.mark.parametrize("name", sorted({**SNIPPETS, **CROSS_SNIPPETS}))
def test_prediction_matches_odoo_on_every_python(results, name):
    actual = {version for version, snippets in results.items() if snippets[name]["rejected"]}
    for version, snippets in results.items():
        if snippets[name]["rejected"]:
            continue
        predicted = set(snippets[name]["predicted"]) & set(results)
        assert predicted == actual, f"seen from Python {version}"
