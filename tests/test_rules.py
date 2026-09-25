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


def test_usererror_in_other_branch_is_fine():
    code = "if records:\n    records.write({'a': 1})\nelse:\n    raise UserError('nothing')"
    assert codes(code) == []
    helper = "def done(r):\n    r.write({'a': 1})\nif not records:\n    raise UserError('x')\ndone(records)"
    assert codes(helper) == []


def test_usererror_after_write_in_loop_and_try():
    loop = "for r in records:\n    if r.x:\n        raise UserError('bad')\n    r.write({'a': 1})"
    assert codes(loop) == [(3, "W303")]
    handler = "try:\n    records.write({'a': 1})\nexcept Exception:\n    raise UserError('x')"
    assert codes(handler) == [(4, "W303")]


def test_command_create_is_not_a_write():
    code = "cmds = [Command.create({'a': 1}), Command.unlink(2)]\nif not cmds:\n    raise UserError('x')"
    assert codes(code) == []


def test_record_names_in_local_scopes_are_not_context():
    code = "ids = [record.id for record in model.search([])]\nf = lambda records: records\ndef g(record):\n    return record"
    assert codes(code, caller="cron") == []
    assert codes(code, binding="list") == []


def test_cron_records_used_before_assignment():
    code = "for r in records:\n    pass\nrecords = model.search([])"
    assert codes(code, caller="cron") == [(1, "W304")]


def test_query_in_lambda_and_helper():
    code = ("def count(p):\n    return env['x'].search_count([('p', '=', p.id)])\n"
            "a = records.filtered(lambda r: env['y'].search_count([]))\n"
            "for r in records:\n    n = count(r)\n")
    assert codes(code) == [(3, "W302"), (5, "W302")]
    assert codes("x = env['a'].formatted_read_group([], ['b'])") == []
    assert codes("for r in records:\n    x = env['a'].formatted_read_group([], ['b'])") == [(2, "W302")]


def test_batch_search_in_while_is_fine():
    code = "while True:\n    batch = model.search([('done', '=', False)], limit=100)\n    if not batch:\n        break"
    assert codes(code, caller="cron") == []


def test_commit_rules():
    assert [c for _, c in codes("cr = env.cr\ncr.commit()")] == ["W301"]
    assert "discards" in lint_code("env.cr.rollback()", "19.0")[0].message
    batch = "while True:\n    b = model.search([], limit=10)\n    if not b:\n        break\n    env.cr.commit()"
    assert codes(batch, caller="cron") == []
    assert "_commit_progress" in lint_code("env.cr.commit()", "19.0", "cron")[0].message


def test_exception_caught_locally():
    code = "for r in records:\n    try:\n        raise Exception('skip')\n    except Exception as e:\n        log(str(e))"
    assert codes(code) == []


def test_kanban_binding_on_19_only():
    code = "action = record.open()"
    assert [c for _, c in codes(code, binding="kanban,form")] == ["W305"]
    assert [d.code for d in lint_code(code, "18.0", binding="kanban,form")] == []
