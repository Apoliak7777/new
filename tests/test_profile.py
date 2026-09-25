import pytest

from sevlint import profile


@pytest.mark.parametrize("raw, expected", [
    ("19", "19.0"), ("19.0", "19.0"), ("19.0.1.0.0", "19.0"), (19, "19.0"), (17.0, "17.0"),
    ("saas-19.2", "saas-19.2"), ("saas~19.2", "saas-19.2"), ("19.2", "saas-19.2"), ("SAAS~17.1", "saas-17.1"),
])
def test_normalize_version(raw, expected):
    assert profile.normalize_version(raw) == expected


def test_versions_are_ordered_and_complete():
    versions = profile.available_versions()
    assert versions == sorted(versions, key=profile.version_key)
    assert {"17.0", "18.0", "19.0", "20.0", "saas-19.2", "saas-19.4"} <= set(versions)
    assert profile.version_key("saas-19.2") < profile.version_key("20.0")


def test_sandbox_profiles():
    assert profile.load("19.0").sandbox_policy is None
    assert profile.load("saas-19.3").sandbox_policy == "log"
    assert profile.load("20.0").python_min == (3, 12)


def test_python_range_text():
    assert profile.load("saas-17.3").python_range == "3.10+"
    assert profile.load("saas-19.2").python_range == "3.12-3.14"
