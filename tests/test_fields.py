import ast

from sevlint import fields
from sevlint.linter import Options, lint_code, lint_paths


def codes(code, version="19.0", model=None):
    return [(d.line, d.code) for d in fields.check_fields(ast.parse(code), version, model)]


def test_model_from_xmlid():
    assert fields.model_from_xmlid("base.model_res_users") == "res.users"
    assert fields.model_from_xmlid("model_sale_order_line") == "sale.order.line"
    assert fields.model_from_xmlid("base.group_user") is None


def test_renamed_fields_are_errors_only_where_renamed():
    code = "users = env['res.users'].search([('groups_id', 'in', [1])])"
    assert codes(code, "19.0") == [(1, "E203")]
    assert codes(code, "saas-18.2") == [(1, "E203")]
    assert codes(code, "18.0") == []
    assert codes("u = env['res.users'].browse(1)\nx = u.group_ids", "17.0") == [(2, "E203")]


def test_every_field_position():
    code = ("lines = env['sale.order.line'].sudo().search([('tax_id', '=', 1)])\n"
            "lines.write({'tax_id': False})\n"
            "env['sale.order.line'].create([{'tax_id': False}])\n"
            "names = lines.mapped('tax_id.name')\n"
            "x = lines.filtered('tax_id')\n"
            "rows = lines.read(['tax_id'])\n"
            "data = env['sale.order.line'].search_read([], ['tax_id'])\n"
            "y = lines[0]['tax_id']\n"
            "for line in lines:\n    z = line.tax_id\n")
    assert [line for line, c in codes(code)] == list(range(1, 9)) + [10]


def test_removed_fields_and_models_are_warnings():
    assert codes("l = env['crm.lead'].browse(1)\nm = l.mobile") == [(2, "W203")]
    assert codes("c = env['hr.contract'].search([])") == [(1, "W205")]


def test_unknown_names_are_ignored():
    code = ("p = env['res.partner'].browse(1)\n"
            "a = p.x_studio_field\nb = p.some_custom_field\nc = p.action_archive()\n"
            "d = env['my.custom.model'].search([('foo', '=', 1)])")
    assert codes(code) == []


def test_type_inference():
    assert codes("x = user.groups_id") == [(1, "E203")]
    assert codes("x = env.user.groups_id") == [(1, "E203")]
    assert codes("x = record.groups_id", model="res.users") == [(1, "E203")]
    assert codes("x = record.groups_id") == []  # model unknown
    assert codes("def f(u):\n    return u.groups_id") == []  # parameters are not inferred
    conflicting = "u = env['res.users'].browse(1)\nu = env['res.partner'].browse(1)\nx = u.groups_id"
    assert codes(conflicting) == []


def test_xml_model_id_gives_record_its_model(tmp_path):
    path = tmp_path / "a.xml"
    path.write_text('<odoo><record id="a" model="ir.actions.server">'
                    '<field name="model_id" ref="base.model_res_users"/><field name="state">code</field>'
                    '<field name="code">x = record.groups_id</field></record></odoo>')
    report = lint_paths([str(path)], Options(odoo="19.0"))
    assert [f.code for f in report.findings] == ["E203"]
    assert lint_paths([str(path)], Options(odoo="18.0")).findings == []


def test_header_model_key():
    assert [d.code for d in lint_code("x = records.groups_id", "19.0", model="res.users")] == ["E203"]


def test_sorted_order_spec():
    code = "lines = env['sale.order.line'].search([])\nx = lines.sorted('tax_id desc, id')\n"
    assert codes(code) == [(2, "E203")]


def test_delegate_true_is_delegation():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import fields_index
    (parsed,) = fields_index.parse_models(
        "class Cron(models.Model):\n"
        "    _name = 'ir.cron'\n"
        "    ir_actions_server_id = fields.Many2one('ir.actions.server', delegate=True, required=True)\n"
        "    other_id = fields.Many2one(comodel_name='res.partner', delegate=True)\n"
        "    plain_id = fields.Many2one('res.users')\n")
    assert parsed[3] == {"ir.actions.server", "res.partner"}
    versions, index = fields._index()
    assert all(index["ir.cron"]["model_id"] >> i & 1 for i in range(len(versions)))
