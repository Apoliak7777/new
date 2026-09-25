from sevlint.linter import lint_code


def codes(code, caller="server_action", binding=None):
    return [(d.line, d.code) for d in lint_code(code, "19.0", caller, binding=binding)]


def test_cr_commit():
    assert codes("env.cr.commit()\nrecord.env.cr.rollback()") == [(1, "W301"), (2, "W301")]


def test_query_in_for_loop_and_comprehension():
    code = (
        "for r in records:\n"
        "    n = env['sale.order'].search_count([('partner_id', '=', r.id)])\n"
        "xs = [env['res.partner'].sudo().search([('id', '=', i)]) for i in range(3)]\n"
        "ys = env['res.partner'].search([])\n"
    )
    assert codes(code) == [(2, "W302"), (3, "W302")]


def test_query_in_loop_iterable_is_fine():
    assert codes("for p in env['res.partner'].search([]):\n    x = p.name") == []


def test_query_in_while_condition():
    assert codes("while env['x'].search_count([]):\n    break") == [(1, "W302")]


def test_usererror_after_write():
    code = "records.write({'a': 1})\nraise UserError('done')"
    assert codes(code) == [(2, "W303")]


def test_usererror_without_write_is_fine():
    assert codes("x = records.mapped('name')\nraise UserError(str(x))") == []


def test_usererror_before_write_is_fine():
    assert codes("if not records:\n    raise UserError('none')\nrecords.write({'a': 1})") == []


def test_cron_record_usage():
    assert codes("for r in records:\n    r.write({'a': 1})", caller="cron") == [(1, "W304")]
    assert codes("records = model.search([])\nrecords.write({'a': 1})", caller="cron") == []
    assert codes("records.write({'a': 1})", caller="server_action") == []


def test_first_record_only_when_bound_to_list_views():
    code = "x = 1\naction = record.action_open()"
    assert codes(code) == []
    assert codes(code, binding="form") == []
    assert codes(code, binding="list,form") == [(2, "W305")]
    assert codes("for r in records:\n    y = record", binding="list") == []
    assert codes(code, caller="automation", binding="list") == []


def test_raise_exception():
    assert codes("raise Exception('boom')") == [(1, "W306")]
    assert codes("try:\n    x = 1\nexcept Exception:\n    raise UserError('x')") == []
