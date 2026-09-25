import textwrap
from pathlib import Path

from sevlint import sources
from sevlint.linter import Options, lint_paths

XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <odoo>
        <record id="action_plain" model="ir.actions.server">
            <field name="name">Plain</field>
            <field name="model_id" ref="base.model_res_partner"/>
            <field name="state">code</field>
            <field name="code">
    for r in records:
        r.name = 'x'
            </field>
        </record>
        <record id="action_cdata" model="ir.actions.server">
            <field name="state">code</field>
            <field name="code"><![CDATA[
    if records and 1 < 2:
        import os
    ]]></field>
        </record>
        <record id="action_entities" model="ir.actions.server">
            <field name="state">code</field>
            <field name="code">x = 1 &lt; 2 and records
    y = missing_name</field>
        </record>
        <record id="action_bound_list" model="ir.actions.server">
            <field name="state">code</field>
            <field name="binding_model_id" ref="base.model_res_partner"/>
            <field name="code">action = record.open()</field>
        </record>
        <record id="action_bound_form" model="ir.actions.server">
            <field name="state">code</field>
            <field name="binding_model_id" ref="base.model_res_partner"/>
            <field name="binding_view_types">form</field>
            <field name="code">action = record.open()</field>
        </record>
        <record id="action_automation" model="ir.actions.server">
            <field name="state">code</field>
            <field name="base_automation_id" ref="rule_1"/>
            <field name="code">x = records</field>
        </record>
        <record id="action_object_write" model="ir.actions.server">
            <field name="state">object_write</field>
            <field name="code">import os</field>
        </record>
        <record id="cron_1" model="ir.cron">
            <field name="code">records.write({'a': 1})</field>
        </record>
        <record id="partner" model="res.partner">
            <field name="code">import os</field>
        </record>
    </odoo>
""")


def test_read_xml_snippets_and_callers():
    snippets, problems = sources.read_xml("m.xml", XML.encode())
    assert problems == []
    assert [(s.label, s.caller) for s in snippets] == [
        ("action_plain", "server_action"),
        ("action_cdata", "server_action"),
        ("action_entities", "server_action"),
        ("action_bound_list", "server_action"),
        ("action_bound_form", "server_action"),
        ("action_automation", "automation"),
        ("action_object_write", "server_action"),
        ("cron_1", "cron"),
    ]
    assert "1 < 2" in snippets[2].code
    assert [s.binding for s in snippets[3:5]] == ["list,form", "form"]
    # Odoo validates the code of every action on save, whatever its state
    assert [s.save_time_only for s in snippets] == [False] * 6 + [True, False]


def test_xml_line_numbers(tmp_path):
    path = tmp_path / "m.xml"
    path.write_text(XML)
    report = lint_paths([str(path)], Options())
    lines = XML.splitlines()
    found = {(f.label, f.code): f.line for f in report.findings}
    assert "r.name = 'x'" in lines[found[("action_plain", "E101")] - 1]
    assert "import os" in lines[found[("action_cdata", "E101")] - 1]
    assert "missing_name" in lines[found[("action_entities", "E201")] - 1]
    assert "records.write" in lines[found[("cron_1", "W304")] - 1]
    assert ("action_bound_list", "W305") in found and ("action_bound_form", "W305") not in found
    assert ("action_object_write", "E101") in found  # save-time check still applies


def test_xml_parse_error_and_empty_file():
    assert sources.read_xml("bad.xml", b"<odoo><record>")[1][0].startswith("bad.xml: XML parse error")
    assert sources.read_xml("empty.xml", b"") == ([], [])


def test_header_parsing():
    header = sources.parse_header("# sevlint: odoo=18 caller=cron modules=website,mail names=a disable=W302 binding=list\nx = 1")
    assert header.binding == "list"
    assert (header.odoo, header.caller) == ("18.0", "cron")
    assert header.modules == {"website", "mail"}
    assert header.names == {"a"} and header.disabled == {"W302"}
    assert sources.parse_header("x = 1") is None
    bad = sources.parse_header("# sevlint: caller=nope foo")
    assert len(bad.errors) == 2


def test_python_files_need_header_unless_all_py(tmp_path):
    (tmp_path / "plain.py").write_text("import os\n")
    (tmp_path / "sa.py").write_text("# sevlint: odoo=19.0\nimport os\n")
    report = lint_paths([str(tmp_path)], Options())
    assert [(f.path.endswith("sa.py"), f.line) for f in report.findings] == [(True, 2)]
    report = lint_paths([str(tmp_path)], Options(all_py=True))
    assert len(report.findings) == 2


def make_module(root, name, version, depends):
    mod = root / name
    (mod / "data").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(repr({"name": name, "version": version, "depends": depends}))
    return mod


def test_manifest_version_and_dependencies(tmp_path):
    make_module(tmp_path, "website", "17.0.1.0", ["base"])
    shop = make_module(tmp_path, "my_shop", "17.0.1.0.0", ["website"])
    xml = shop / "data" / "a.xml"
    xml.write_text('<odoo><record id="a" model="ir.actions.server"><field name="code">x = request</field></record></odoo>')
    assert sources.manifest_version(xml) == "17.0"
    assert sources.manifest_modules(xml) == {"my_shop", "website", "base"}
    report = lint_paths([str(xml)], Options())
    assert report.findings == [] and report.versions == {"17.0"}


def test_manifest_without_series_prefix_is_ignored(tmp_path):
    mod = make_module(tmp_path, "m", "1.0", [])
    assert sources.manifest_version(mod / "data" / "x.xml") is None


def _snippets(xml):
    snippets, problems = sources.read_xml("x.xml", xml.encode())
    assert problems == []
    return snippets


def test_nested_automation_action_records():
    xml = """<odoo>
    <record id="rule" model="base.automation">
        <field name="name">Rule</field>
        <field name="action_server_ids">
            <record id="rule_action" model="ir.actions.server">
                <field name="state">code</field>
                <field name="code">record.x = 1</field>
            </record>
        </field>
    </record>
</odoo>"""
    (snippet,) = _snippets(xml)
    assert (snippet.label, snippet.caller, snippet.first_line) == ("rule_action", "automation", 7)


def test_eval_attributes():
    xml = """<odoo>
    <record id="c" model="ir.cron">
        <field name="state" eval="'code'"/>
        <field name="code" eval="'model._run()'"/>
    </record>
    <record id="s" model="ir.actions.server">
        <field name="state" eval="'object_write'"/>
        <field name="code">x = 1</field>
    </record>
    <record id="u" model="ir.actions.server">
        <field name="binding_model_id" eval="False"/>
        <field name="code">x = record</field>
    </record>
    <record id="v" model="ir.actions.server">
        <field name="binding_model_id" ref="base.model_res_partner"/>
        <field name="binding_view_types" eval="'form'"/>
        <field name="code">x = record</field>
    </record>
    <record id="w" model="ir.actions.server">
        <field name="code" eval="compute_me()"/>
    </record>
</odoo>"""
    snippets = _snippets(xml)
    # no state on ir.actions.server: 17/18 default to object_write, 19 has no default -> code never runs
    assert [(s.label, s.code, s.save_time_only, s.binding) for s in snippets] == [
        ("c", "model._run()", False, None),
        ("s", "x = 1", True, None),
        ("u", "x = record", True, None),
        ("v", "x = record", True, "form"),
    ]


def test_text_after_comment_is_dropped_like_odoo(tmp_path):
    xml = """<odoo>
    <record id="a" model="ir.actions.server">
        <field name="code">x = 1
<!-- a comment -->
import os</field>
    </record>
</odoo>"""
    (snippet,) = _snippets(xml)
    assert "import os" not in snippet.code and [f[:2] for f in snippet.source_findings] == [(5, "W100")]
    path = tmp_path / "a.xml"
    path.write_text(xml)
    assert [(f.line, f.code) for f in lint_paths([str(path)], Options()).findings] == [(5, "W100")]


def test_repeated_code_field_last_wins():
    xml = """<odoo><record id="a" model="ir.actions.server">
        <field name="code">x = (</field>
        <field name="code">x = 1</field>
    </record></odoo>"""
    (snippet,) = _snippets(xml)
    assert snippet.code == "x = 1"


def test_header_only_in_leading_comment_block():
    assert sources.parse_header("# comment\n\n# sevlint: odoo=18\nx = 1").odoo == "18.0"
    assert sources.parse_header("x = 1\n# sevlint: disable=W302\n") is None


def test_bom_python_file(tmp_path):
    path = tmp_path / "sa.py"
    path.write_bytes("\ufeff# sevlint: odoo=19.0\nimport os\n".encode("utf-8"))
    report = lint_paths([str(path)], Options())
    assert [(f.line, f.code) for f in report.findings] == [(2, "E101")]


def test_symlinked_modules_are_walked(tmp_path):
    real = tmp_path / "repo"
    make_module(real, "website", "17.0.1.0", [])
    make_module(real, "shop", "17.0.1.0", ["website"])
    (real / "shop" / "data" / "a.xml").write_text(
        '<odoo><record id="a" model="ir.actions.server"><field name="code">x = request.x</field></record></odoo>')
    addons = tmp_path / "addons"
    addons.mkdir()
    for name in ("website", "shop"):
        (addons / name).symlink_to(real / name, target_is_directory=True)
    (addons / "loop").symlink_to(addons, target_is_directory=True)
    report = lint_paths([str(addons)], Options())
    assert report.snippets == 1 and report.findings == [] and report.versions == {"17.0"}


def test_unsupported_explicit_file_is_a_note(tmp_path):
    (tmp_path / "icon.svg").write_text("<svg/>")
    report = lint_paths([str(tmp_path / "icon.svg")], Options())
    assert report.problems == [] and report.notes


def test_unsupported_version_does_not_abort_the_run(tmp_path):
    (tmp_path / "a.py").write_text("# sevlint: odoo=16.0\nx = 1\n")
    (tmp_path / "b.py").write_text("# sevlint: odoo=19.0\nimport os\n")
    report = lint_paths([str(tmp_path)], Options())
    assert len(report.problems) == 1 and "unsupported Odoo version" in report.problems[0]
    assert [f.code for f in report.findings] == ["E101"]


def test_unreadable_file_is_a_problem(tmp_path, monkeypatch):
    path = tmp_path / "a.xml"
    path.write_text("<odoo/>")
    monkeypatch.setattr(type(path), "read_bytes", lambda self: (_ for _ in ()).throw(PermissionError(13, "denied")))
    report = lint_paths([str(path)], Options())
    assert report.problems and "cannot read" in report.problems[0]


def test_all_code_after_leading_comment(tmp_path):
    path = tmp_path / "a.xml"
    path.write_text('<odoo><record id="a" model="ir.actions.server"><field name="state">code</field>\n'
                    '<field name="code">\n    <!-- archive -->\nrecords.write({"active": False})\n</field></record></odoo>')
    assert [(f.line, f.code) for f in lint_paths([str(path)], Options()).findings] == [(4, "W100")]


def test_w100_inline_suppression(tmp_path):
    path = tmp_path / "a.xml"
    path.write_text('<odoo><record id="a" model="ir.actions.server"><field name="code">x = 1\n<!-- c -->\n'
                    'y = 2  # sevlint: disable=W100\n</field></record></odoo>')
    assert lint_paths([str(path)], Options()).findings == []


def test_child_element_in_code_field_is_an_error(tmp_path):
    path = tmp_path / "a.xml"
    path.write_text('<odoo><record id="a" model="ir.actions.server"><field name="code">x = 1\n<span/>\n'
                    'import os\n</field></record></odoo>')
    assert [(f.line, f.code) for f in lint_paths([str(path)], Options()).findings] == [(2, "E003")]


def test_encodings(tmp_path):
    body = '<odoo><record id="a" model="ir.actions.server"><field name="name">{}</field>' \
           '<field name="state">code</field><field name="code">import os</field></record></odoo>'
    cases = {"sjis.xml": ('<?xml version="1.0" encoding="Shift_JIS"?>\n' + body.format("日本")).encode("shift_jis"),
             "utf8.xml": ('<?xml version="1.0" encoding="utf8"?>\n' + body.format("Café")).encode("utf-8"),
             "u16.xml": ('<?xml version="1.0" encoding="UTF-16"?>\n' + body.format("č")).encode("utf-16"),
             "latin.xml": ('<?xml version="1.0" encoding="ISO-8859-2"?>\n' + body.format("č")).encode("iso-8859-2")}
    for name, data in cases.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "bad.xml").write_bytes(b'<?xml version="1.0" encoding="latin-9x"?>\n<odoo/>')
    (tmp_path / "b64.xml").write_bytes(b'<?xml version="1.0" encoding="base64"?>\n<odoo/>')
    report = lint_paths([str(tmp_path)], Options())
    assert sorted(Path(f.path).name for f in report.findings) == sorted(cases)
    assert len(report.problems) == 2 and all("cannot decode" in p for p in report.problems)


def test_unhashable_eval_does_not_crash():
    xml = '<odoo><record id="a" model="ir.actions.server"><field name="state">code</field>' \
          '<field name="binding_model_id" ref="m"/><field name="binding_view_types" eval="{[\'list\']: 1}"/>' \
          '<field name="code">x = 1</field></record></odoo>'
    (snippet,) = _snippets(xml)
    assert snippet.binding is None


def test_code_from_file_attribute(tmp_path):
    mod = make_module(tmp_path, "mymod", "19.0.1.0.0", [])
    (mod / "data" / "code.py").write_text("import os\n")
    xml = mod / "data" / "a.xml"
    xml.write_text('<odoo><record id="a" model="ir.actions.server"><field name="state">code</field>'
                   '<field name="code" type="char" file="mymod/data/code.py"/></record></odoo>')
    report = lint_paths([str(xml)], Options())
    assert [(Path(f.path).name, f.line, f.code) for f in report.findings] == [("code.py", 1, "E101")]


def test_bare_disable_in_header_block_is_not_an_error():
    header = sources.parse_header("# sevlint: disable\nimport os\n")
    assert header is not None and header.errors == []
