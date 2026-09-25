"""sevlint vs. Odoo's own safe_eval.py on the running interpreter."""
import pytest

import oracle
from corpus import SNIPPETS
from sevlint import engine, profile

VERSIONS = profile.available_versions()
SAVE_TIME_CODES = {"E001", "E101", "E102"}


def sevlint_rejects(version: str, code: str) -> bool:
    analysis = engine.analyse(code)
    diags = analysis.diagnostics + engine.check_save_time(analysis, profile.load(version))
    return any(d.code in SAVE_TIME_CODES for d in diags)


@pytest.mark.parametrize("version", VERSIONS)
def test_opcode_set_matches_odoo(version):
    assert profile.load(version).safe_opcodes == oracle.load(version)._SAFE_OPCODES


@pytest.mark.parametrize("version", VERSIONS)
def test_unsafe_attributes_match_odoo(version):
    assert profile.load(version).unsafe_attributes == set(oracle.load(version)._UNSAFE_ATTRIBUTES)


@pytest.mark.parametrize("version", VERSIONS)
def test_builtins_match_odoo(version):
    assert profile.load(version).builtins == oracle.runtime_builtins(version)


@pytest.mark.parametrize("version", VERSIONS)
def test_wrapped_modules_match_odoo(version):
    module = oracle.load(version)
    for name, attrs in profile.load(version).wrapped_modules.items():
        wrapped = getattr(module, name)
        exposed = {a for a in vars(wrapped) if not a.startswith("_")}
        assert exposed == set(attrs), name
        for attr, sub in attrs.items():
            if sub is not None:
                assert {a for a in vars(getattr(wrapped, attr)) if not a.startswith("_")} == set(sub), f"{name}.{attr}"


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("name", sorted(SNIPPETS))
def test_save_time_verdict_matches_odoo(version, name):
    code = SNIPPETS[name]
    assert sevlint_rejects(version, code) == oracle.rejects_on_save(version, code)


def test_dunder_string_literal_is_accepted_by_odoo():
    # A common belief is that '__X__' inside a string blocks saving; Odoo only checks co_names.
    for version in VERSIONS:
        assert not oracle.rejects_on_save(version, SNIPPETS["dunder_string_literal"])
