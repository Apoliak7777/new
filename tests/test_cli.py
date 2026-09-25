import io
import json
import sys

import pytest

from sevlint import cli


def run(argv, stdin="", monkeypatch=None, capsys=None):
    if monkeypatch is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
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
    assert code == 0 and out.startswith("E101:")
    code, out, _ = run(["versions"], capsys=capsys)
    assert code == 0 and "19.0  odoo/odoo@" in out
