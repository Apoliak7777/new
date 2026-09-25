"""sevlint vs. Odoo's own safe_eval on the running interpreter, for every vendored version."""
import sys

import pytest

import oracle
from corpus import SNIPPETS
from sevlint import profile
from sevlint.linter import lint_code

VERSIONS = profile.available_versions()
SANDBOX = [v for v in VERSIONS if oracle.has_sandbox(v)]
SAVE_TIME_CODES = {"E001", "E004", "E101", "E102"}


def loadable(version):
    if oracle.has_sandbox(version) and sys.version_info < (3, 12):
        pytest.skip("Odoo's sandboxed safe_eval needs Python 3.12+ (sys.monitoring), like Odoo itself")
    return version


def sevlint_rejects(version: str, code: str, policy: str | None = None) -> bool:
    return any(d.code in SAVE_TIME_CODES for d in lint_code(code, version, unsafe_policy=policy))


@pytest.mark.parametrize("version", VERSIONS)
def test_opcode_set_matches_odoo(version):
    assert profile.load(version).safe_opcodes == oracle.load(loadable(version))._SAFE_OPCODES


@pytest.mark.parametrize("version", VERSIONS)
def test_unsafe_attributes_match_odoo(version):
    assert profile.load(version).unsafe_attributes == set(oracle.load(loadable(version))._UNSAFE_ATTRIBUTES)


@pytest.mark.parametrize("version", VERSIONS)
def test_builtins_match_odoo(version):
    assert profile.load(version).builtins == oracle.runtime_builtins(loadable(version))


@pytest.mark.parametrize("version", VERSIONS)
def test_wrapped_modules_match_odoo(version):
    module = oracle.load(loadable(version))
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
    assert sevlint_rejects(version, code) == oracle.rejects_on_save(loadable(version), code)


@pytest.mark.parametrize("policy", ["disable", "log", "raise", "terminate"])
@pytest.mark.parametrize("version", SANDBOX)
@pytest.mark.parametrize("name", sorted(SNIPPETS))
def test_sandbox_policies_match_odoo(version, policy, name):
    code = SNIPPETS[name]
    assert sevlint_rejects(version, code, policy) == oracle.rejects_on_save(loadable(version), code, policy)


def test_dunder_string_literal_is_accepted_by_odoo():
    # A common belief is that '__X__' inside a string blocks saving; Odoo only checks co_names.
    for version in VERSIONS:
        if not oracle.has_sandbox(version) or sys.version_info >= (3, 12):
            assert not oracle.rejects_on_save(version, SNIPPETS["dunder_string_literal"])
