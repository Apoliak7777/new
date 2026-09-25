import io
import re
import json
import sys

import pytest

from sevlint import cli


def run(argv, stdin="", monkeypatch=None, capsys=None):
    if monkeypatch is not None:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8")), encoding="utf-8"))
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_check_clean_file_exit_0(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("# sevlint: odoo=19.0\nx = records\n")
    code, out, err = run(["check", "a.py"], capsys=capsys)
    assert code == 0 and out == "" and "0 error(s)" in err


def test_check_errors_exit_1_text_format(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("# sevlint: odoo=17.0 caller=cron\nimport os\n")
    code, out, err = run(["check", "a.py"], capsys=capsys)
    assert code == 1
    assert out.startswith("a.py:2: E101 import statement") and "[17.0 cron]" in out


def test_stdin_json_format(capsys, monkeypatch):
    code, out, _ = run(["check", "-", "--format", "json", "--odoo", "18"], "x = type(1)\n", monkeypatch, capsys)
    data = json.loads(out)
    assert code == 1
    assert data["summary"]["errors"] == 1
    assert data["findings"][0]["code"] == "E201" and data["findings"][0]["odoo_version"] == "18.0"


def test_github_format(capsys, monkeypatch):
    code, out, _ = run(["check", "-", "--format", "github"], "for r in records:\n    env['a'].search([])\n",
                       monkeypatch, capsys)
    assert code == 0
    assert out.startswith("::warning file=<stdin>,line=2,title=sevlint W302::")


def test_strict_fails_on_warnings(capsys, monkeypatch):
    code, *_ = run(["check", "-", "--strict"], "env.cr.commit()\n", monkeypatch, capsys)
    assert code == 1


def test_modules_names_disable_options(capsys, monkeypatch):
    src = "x = json.dumps(foo)\nenv.cr.commit()\n"
    code, out, _ = run(["check", "-", "--modules", "website", "--names", "foo", "--disable", "W301", "--strict"],
                       src, monkeypatch, capsys)
    assert code == 0 and out == ""


def test_config_file(tmp_path, capsys, monkeypatch):
    pytest.importorskip("tomllib" if sys.version_info >= (3, 11) else "tomli")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.sevlint]\nodoo = "17.0"\nnames = ["foo"]\ndisable = ["W*"]\n')
    (tmp_path / "a.py").write_text("# sevlint:\nx = foo\nenv.cr.commit()\n")
    code, out, err = run(["check", "a.py", "--strict", "--format", "json"], capsys=capsys)
    data = json.loads(out)
    assert code == 0 and data["findings"] == []


def test_config_unknown_key(tmp_path, capsys, monkeypatch):
    pytest.importorskip("tomllib" if sys.version_info >= (3, 11) else "tomli")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".sevlint.toml").write_text('odo = "17.0"\n')
    code, _, err = run(["check", "-"], capsys=capsys, monkeypatch=monkeypatch)
    assert code == 2 and "unknown key" in err


def test_target_python_mismatch(capsys, monkeypatch):
    code, _, err = run(["check", "-", "--target-python", "2.7"], "x = 1\n", monkeypatch, capsys)
    assert code == 2 and "uvx --python 2.7" in err


def test_target_python_match(capsys, monkeypatch):
    running = "%d.%d" % sys.version_info[:2]
    code, *_ = run(["check", "-", "--target-python", running], "x = 1\n", monkeypatch, capsys)
    assert code == 0


def test_unknown_odoo_version(capsys, monkeypatch):
    code, _, err = run(["check", "-", "--odoo", "12.0"], "x = 1\n", monkeypatch, capsys)
    assert code == 2 and "unsupported Odoo version" in err


def test_missing_file_is_a_problem(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(["check", "nope.py"], capsys=capsys)
    assert code == 1 and "no such file" in err


def test_explain_and_versions(capsys):
    code, out, _ = run(["explain", "e101"], capsys=capsys)
    assert code == 0 and out.startswith("E101 forbidden-opcode:")
    code, out, _ = run(["versions"], capsys=capsys)
    assert code == 0 and re.search(r"^19\.0 +odoo/odoo@", out, re.M) and "saas-19.3" in out


def _needs_toml():
    pytest.importorskip("tomllib" if sys.version_info >= (3, 11) else "tomli")


def test_config_is_found_per_linted_path(tmp_path, capsys, monkeypatch):
    _needs_toml()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / ".sevlint.toml").write_text('names = ["foo"]\n')
    (tmp_path / "a" / "x.py").write_text("# sevlint:\nx = foo\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "y.py").write_text("# sevlint:\nx = foo\n")
    code, out, _ = run(["check", "a/x.py", "b/y.py"], capsys=capsys)
    assert code == 1 and "a/x.py" not in out and "b/y.py:2: E201" in out


def test_invalid_toml_and_values_exit_2(tmp_path, capsys, monkeypatch):
    _needs_toml()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("# sevlint:\nx = 1\n")
    for text, needle in (("odoo = \n", "invalid TOML"), ("target-python = 3.10\n", "quoted version"),
                         ('caller = "scheduled"\n', "'caller' must be"), ('odoo = "12.0"\n', "unsupported")):
        (tmp_path / ".sevlint.toml").write_text(text)
        code, _, err = run(["check", "x.py"], capsys=capsys)
        assert code == 2 and needle in err, text


def test_github_escaping(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data,v2").mkdir()
    (tmp_path / "data,v2" / "a:b.py").write_text("# sevlint:\nimport os\n")
    code, out, _ = run(["check", "data,v2", "--format", "github"], capsys=capsys)
    assert code == 1 and out.startswith("::error file=data%2Cv2/a%3Ab.py,line=2,title=sevlint E101::")


def test_notes_do_not_fail(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "icon.svg").write_text("<svg/>")
    code, _, err = run(["check", "icon.svg"], capsys=capsys)
    assert code == 0 and "skipped" in err


def test_missing_directory_and_stdin_mix(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(["check", "addosn"], capsys=capsys)
    assert code == 1 and "no such file or directory" in err
    code, _, err = run(["check", "-", "a.py"], capsys=capsys)
    assert code == 2 and "cannot be combined" in err


def test_nested_config_found_when_walking_a_directory(tmp_path, capsys, monkeypatch):
    _needs_toml()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / ".sevlint.toml").write_text('names = ["foo"]\nodoo = "17.0"\n')
    (tmp_path / "p" / "x.py").write_text("# sevlint:\nx = foo\n")
    code, out, _ = run(["check", ".", "--format", "json"], capsys=capsys)
    data = json.loads(out)
    assert code == 0 and data["findings"] == []


def test_every_target_python_is_checked(tmp_path, capsys, monkeypatch):
    _needs_toml()
    monkeypatch.chdir(tmp_path)
    running = "%d.%d" % sys.version_info[:2]
    for name, target in (("a", running), ("b", "2.7")):
        (tmp_path / name).mkdir()
        (tmp_path / name / ".sevlint.toml").write_text(f'target-python = "{target}"\n')
        (tmp_path / name / "s.py").write_text("# sevlint:\nx = 1\n")
    code, _, err = run(["check", "a", "b"], capsys=capsys)
    assert code == 2 and "target-python 2.7" in err


def test_stdin_is_read_as_utf8(capsys, monkeypatch):
    raw = "x = 'Faktúra č. 1'\nimport os\n".encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="cp1252"))
    code = cli.main(["check", "-"])
    out, _ = capsys.readouterr()
    assert code == 1 and "<stdin>:2: E101" in out


def test_saas_version_and_unsafe_policy_flags(capsys, monkeypatch):
    code, out, _ = run(["check", "-", "--odoo", "19.3", "--unsafe-policy", "raise", "--format", "json"],
                       "try:\n    x = 1\nexcept:\n    pass\n", monkeypatch, capsys)
    data = json.loads(out)
    assert code == 1 and data["findings"][0]["code"] == "E004" and data["findings"][0]["odoo_version"] == "saas-19.3"


def test_unsafe_policy_config_validation(tmp_path, capsys, monkeypatch):
    _needs_toml()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("# sevlint: odoo=20.0\ntry:\n    x = 1\nexcept:\n    pass\n")
    (tmp_path / ".sevlint.toml").write_text('unsafe-policy = "strict"\n')
    code, _, err = run(["check", "x.py"], capsys=capsys)
    assert code == 2 and "unsafe-policy" in err
    (tmp_path / ".sevlint.toml").write_text('unsafe-policy = "raise"\n')
    code, out, _ = run(["check", "x.py"], capsys=capsys)
    assert code == 1 and "E004" in out
