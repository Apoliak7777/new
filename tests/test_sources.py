import textwrap

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
            <field name="code">x = 1 &lt; 2 and records
    y = missing_name</field>
        </record>
        <record id="action_bound_list" model="ir.actions.server">
            <field name="binding_model_id" ref="base.model_res_partner"/>
            <field name="code">action = record.open()</field>
        </record>
        <record id="action_bound_form" model="ir.actions.server">
            <field name="binding_model_id" ref="base.model_res_partner"/>
            <field name="binding_view_types">form</field>
            <field name="code">action = record.open()</field>
        </record>
        <record id="action_automation" model="ir.actions.server">
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
        ("cron_1", "cron"),
    ]
    assert "1 < 2" in snippets[2].code
    assert [s.binding for s in snippets[3:5]] == ["list,form", "form"]


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
