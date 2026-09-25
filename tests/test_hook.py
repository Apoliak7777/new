import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sevlint.hook import claude_post_tool_use


def run_hook(payload):
    stderr = io.StringIO()
    code = claude_post_tool_use(io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)), stderr)
    return code, stderr.getvalue()


def event(path, tool="Write", cwd=None):
    data = {"hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": {"file_path": str(path)}}
    if cwd:
        data["cwd"] = str(cwd)
    return data


def test_findings_are_fed_back_with_exit_2(tmp_path):
    path = tmp_path / "sa.py"
    path.write_text("# sevlint: odoo=19.0\nrecord.name = 'x'\n")
    code, err = run_hook(event(path))
    assert code == 2
    assert "E101" in err and "sa.py:2" in err


def test_clean_file_is_silent(tmp_path):
    path = tmp_path / "sa.py"
    path.write_text("# sevlint: odoo=19.0\nrecords.write({'name': 'x'})\n")
    assert run_hook(event(path, tool="Edit")) == (0, "")


def test_unrelated_files_are_ignored(tmp_path):
    (tmp_path / "models.py").write_text("import os\n")  # regular Odoo python, no header
    (tmp_path / "notes.md").write_text("import os\n")
    (tmp_path / "view.xml").write_text("<odoo><record model='ir.ui.view' id='v'/></odoo>")
    for name in ("models.py", "notes.md", "view.xml", "missing.xml"):
        assert run_hook(event(tmp_path / name)) == (0, "")


def test_relative_path_uses_cwd(tmp_path):
    (tmp_path / "sa.py").write_text("# sevlint:\nx = type(1)\n")
    code, err = run_hook(event("sa.py", cwd=tmp_path))
    assert code == 2 and "E201" in err


def test_bad_input_never_breaks_the_session():
    assert run_hook("not json") == (0, "")
    assert run_hook({"tool_input": {}}) == (0, "")
    assert run_hook({}) == (0, "")


def test_output_is_capped(tmp_path):
    path = tmp_path / "sa.py"
    path.write_text("# sevlint:\n" + "\n".join(f"x{i} = missing_{i}" for i in range(500)))
    code, err = run_hook(event(path))
    assert code == 2 and len(err) < 10_000 and "... and " in err


ROOT = Path(__file__).resolve().parent.parent


class _BinaryStdin(io.TextIOWrapper):
    """A text stdin whose locale encoding cannot decode the UTF-8 JSON (like cp1252 on Windows)."""


def test_utf8_payload_is_read_as_bytes(tmp_path):
    path = tmp_path / "sa.py"
    path.write_text("# sevlint:\nx = 'čďťľ'\nimport os\n", encoding="utf-8")
    payload = json.dumps({**event(path), "tool_input": {"file_path": str(path), "content": "ďÁ"}},
                         ensure_ascii=False).encode("utf-8")
    stdin = _BinaryStdin(io.BytesIO(payload), encoding="cp1252", errors="strict")
    stderr = io.StringIO()
    assert claude_post_tool_use(stdin, stderr) == 2 and "E101" in stderr.getvalue()


def test_problems_and_bad_config_reach_claude(tmp_path):
    bad_xml = tmp_path / "a.xml"
    bad_xml.write_text('<odoo><record model="ir.actions.server"><field name="code">if a < b: x = 1</field></record></odoo>')
    code, err = run_hook(event(bad_xml))
    assert code == 2 and "XML parse error" in err
    (tmp_path / ".sevlint.toml").write_text("odoo = \n")
    ok = tmp_path / "b.py"
    ok.write_text("# sevlint:\nx = 1\n")
    code, err = run_hook(event(ok))
    assert code == 2 and "invalid TOML" in err


def _launcher(tmp_path, path_entries, payload_path):
    env = {"PATH": os.pathsep.join(str(p) for p in path_entries)}
    return subprocess.run(["/bin/sh", str(ROOT / "hooks" / "run.sh")], input=json.dumps(event(payload_path)),
                          capture_output=True, text=True, cwd=tmp_path, env=env)


def test_launcher_skips_broken_python3_and_runs_hook(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").write_text("#!/bin/sh\nexit 9009\n")  # like the Microsoft Store alias
    (bin_dir / "python3").chmod(0o755)
    (bin_dir / "python").symlink_to(sys.executable)
    (bin_dir / "dirname").symlink_to(shutil.which("dirname"))
    path = tmp_path / "sa.py"
    path.write_text("# sevlint:\nimport os\n")
    proc = _launcher(tmp_path, [bin_dir], path)
    assert proc.returncode == 2 and "E101" in proc.stderr


def test_launcher_without_python(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "dirname").symlink_to(shutil.which("dirname"))
    proc = _launcher(tmp_path, [bin_dir], tmp_path / "sa.py")
    assert proc.returncode == 1 and "no Python >= 3.10 found" in proc.stderr


def test_launcher_rejects_unusable_sevlint_python(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "dirname").symlink_to(shutil.which("dirname"))
    (bin_dir / "python3").symlink_to(sys.executable)
    env = {"PATH": str(bin_dir), "SEVLINT_PYTHON": "/nonexistent/python3.100"}
    proc = subprocess.run(["/bin/sh", str(ROOT / "hooks" / "run.sh")], input="{}", capture_output=True, text=True,
                          env=env)
    assert proc.returncode == 1 and "SEVLINT_PYTHON" in proc.stderr


def test_gitattributes_keeps_launcher_lf():
    assert "*.sh text eol=lf" in (ROOT / ".gitattributes").read_text()


def test_hooks_json_uses_launcher():
    data = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    (entry,) = data["hooks"]["PostToolUse"]
    assert entry["matcher"] == "Write|Edit"
    assert entry["hooks"][0]["command"] == 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh"'


def test_non_odoo_and_unsupported_inputs_stay_silent(tmp_path):
    (tmp_path / "frag.xml").write_text("<item>a</item>\n<item>b</item>\n")
    assert run_hook(event(tmp_path / "frag.xml")) == (0, "")
    mod = tmp_path / "old_mod"
    (mod / "data").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(repr({"name": "x", "version": "16.0.1.0.0", "depends": []}))
    (mod / "data" / "a.xml").write_text('<odoo><record id="a" model="ir.actions.server"><field name="state">code'
                                        '</field><field name="code">import os</field></record></odoo>')
    assert run_hook(event(mod / "data" / "a.xml")) == (0, "")


def test_config_is_not_read_for_files_without_server_actions(tmp_path):
    (tmp_path / ".sevlint.toml").write_text("odoo = \n")  # broken, but irrelevant for util.py
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a + b\n")
    assert run_hook(event(tmp_path / "util.py")) == (0, "")


def test_target_python_mismatch_on_clean_file_goes_to_the_user(tmp_path):
    if not config_available():
        return
    (tmp_path / ".sevlint.toml").write_text('target-python = "2.7"\n')
    (tmp_path / "sa.py").write_text("# sevlint:\nx = 1\n")
    code, err = run_hook(event(tmp_path / "sa.py"))
    assert code == 1 and "target-python is 2.7" in err


def test_rules_are_explained_inline(tmp_path):
    path = tmp_path / "sa.py"
    path.write_text("# sevlint:\nimport os\n")
    code, err = run_hook(event(path))
    assert code == 2 and "E101: Forbidden opcode" in err and "sevlint explain" not in err


def config_available():
    from sevlint import config
    return config.tomllib is not None
