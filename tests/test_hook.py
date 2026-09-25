import io
import json
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
    assert code == 2 and len(err) < 10_000 and "more; run `sevlint check" in err


def test_plugin_entry_point(tmp_path):
    script = Path(__file__).resolve().parent.parent / "hooks" / "claude_hook.py"
    path = tmp_path / "sa.py"
    path.write_text("# sevlint:\nimport os\n")
    proc = subprocess.run([sys.executable, str(script)], input=json.dumps(event(path)), capture_output=True,
                          text=True, cwd=tmp_path, env={"PATH": ""})
    assert proc.returncode == 2 and "E101" in proc.stderr
