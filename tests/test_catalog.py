import json
import sys
from pathlib import Path

import pytest

from sevlint import catalog, cli, fields, sources
from sevlint.linter import Options, lint_code, lint_snippet

ROOT = Path(__file__).resolve().parent.parent


def lint_example(rule, code, context):
    if rule.xml:
        snippets, problems = sources.read_xml("example.xml", code.encode())
        assert not problems
        out = []
        for snippet in snippets:
            out += [f.code for f in lint_snippet(snippet, Options(), context.get("odoo", "19.0"))]
            out += [c for _, c, _, _ in snippet.source_findings if c not in out]
        return out
    schema = None
    if "schema" in context:
        models = {m: frozenset(fs) for m, fs in context["schema"].items()}
        schema = fields.LiveSchema(frozenset(models), models)
    return [d.code for d in lint_code(code, context.get("odoo", "19.0"), context.get("caller", "server_action"),
                                      modules=frozenset(context.get("modules", ())), binding=context.get("binding"),
                                      unsafe_policy=context.get("unsafe_policy"), model=context.get("model"),
                                      schema=schema)]


@pytest.mark.parametrize("rule", catalog.RULES, ids=lambda r: r.code)
def test_bad_example_reports_the_rule(rule):
    expected = rule.code
    if rule.code == "W110" and sys.version_info < (3, 12):
        expected = "E101"  # this Python rejects it outright
    assert expected in lint_example(rule, rule.bad, rule.context)


@pytest.mark.parametrize("rule", catalog.RULES, ids=lambda r: r.code)
def test_good_example_is_clean(rule):
    assert lint_example(rule, rule.good, {**rule.context, **rule.good_context}) == []


def test_catalog_covers_every_code():
    assert len(catalog.BY_CODE) == len(catalog.RULES)
    assert set(cli.RULES) == set(catalog.BY_CODE)
    source = "".join(p.read_text() for p in (ROOT / "src" / "sevlint").glob("*.py"))
    import re
    emitted = set(re.findall(r'"([EW]\d{3})"', source)) - {"E999"}
    assert emitted <= set(catalog.BY_CODE), emitted - set(catalog.BY_CODE)


def test_docs_are_current():
    assert (ROOT / "docs" / "rules.md").read_text(encoding="utf-8") == catalog.markdown(), \
        "run: python tools/gen_docs.py"


def test_sarif(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "my dir").mkdir()
    (tmp_path / "my dir" / "a.py").write_text("# sevlint: odoo=19.0\nimport os\nx = type(1)\n")
    code = cli.main(["check", "my dir", "nope.py", "--format", "sarif"])
    out, _ = capsys.readouterr()
    assert code == 1
    data = json.loads(out)
    assert data["version"] == "2.1.0" and data["$schema"].endswith("sarif-2.1.0.json")
    (run,) = data["runs"]
    driver = run["tool"]["driver"]
    assert driver["name"] == "sevlint" and [r["id"] for r in driver["rules"]] == [r.code for r in catalog.RULES]
    for rule in driver["rules"]:
        assert rule["shortDescription"]["text"] and rule["fullDescription"]["text"] and rule["help"]["text"]
        assert len(rule["fullDescription"]["text"]) <= 1024 and rule["helpUri"].endswith("#" + rule["id"].lower())
    results = run["results"]
    assert [(r["ruleId"], r["level"]) for r in results] == [("E101", "error"), ("E201", "error")]
    for r in results:
        assert driver["rules"][r["ruleIndex"]]["id"] == r["ruleId"]
        loc = r["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "my%20dir/a.py"
    assert results[0]["locations"][0]["physicalLocation"]["region"] == {
        "startLine": 2, "startColumn": 1, "endLine": 2, "endColumn": len("import os") + 1}
    invocation = run["invocations"][0]
    assert invocation["executionSuccessful"] is False
    assert any("nope.py" in n["message"]["text"] for n in invocation["toolExecutionNotifications"])


def test_sarif_uri_outside_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli._uri(str(tmp_path / "x" / "a.py")) == "x/a.py"
    elsewhere = Path("/") / "elsewhere" / "a b.py"
    assert cli._uri(str(elsewhere)).startswith("file:///") and "a%20b.py" in cli._uri(str(elsewhere))
    assert cli._uri("ir.actions.server/12") == "ir.actions.server/12"


def test_explain(capsys):
    assert cli.main(["explain", "w305"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("W305 first-record-only:") and "Bad:" in out and "records.action_confirm()" in out
    assert cli.main(["explain"]) == 0
    assert len([l for l in capsys.readouterr().out.splitlines() if l[:1] and l[:1] in "EW"]) == len(catalog.RULES)
