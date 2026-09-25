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


def test_context_read_in_the_reassigning_statement():
    assert codes("records = records.filtered(lambda r: r.active)\nfor rec in records:\n    rec.write({'x': 1})",
                 caller="cron") == [(1, "W304")]
    assert codes("record = record.sudo()\nrecord.write({'x': 1})", binding="list") == [(1, "W305")]


def test_w303_earlier_iterations_headers_helpers_and_lambdas():
    loop_branch = "for o in records:\n    if o.email:\n        o.write({'s': 1})\n    else:\n        raise UserError('x')"
    assert codes(loop_branch) == [(5, "W303")]
    loop_handler = ("for o in records:\n    try:\n        o.action_confirm()\n    except UserError:\n"
                    "        o.write({'f': True})\n    except Exception:\n        raise UserError('u')")
    assert codes(loop_handler) == [(7, "W303")]
    helper_and_lambda = ("def close(o):\n    o.write({'s': 'done'})\n\nfor o in records:\n    close(o)\n"
                         "if records.filtered(lambda o: not o.partner_id):\n    raise UserError('missing')")
    assert codes(helper_and_lambda) == [(7, "W303")]
    header = "for m in env['account.move'].create([{}]):\n    if not m.line_ids:\n        raise UserError('e')"
    assert codes(header) == [(3, "W303")]
    raise_in_helper = "records.write({'a': 1})\ndef check():\n    raise UserError('x')\ncheck()"
    assert codes(raise_in_helper) == [(3, "W303")]
    helper_before = "def notify(r):\n    r.message_post(body='d')\nnotify(record)\nif record.x:\n    raise UserError('x')"
    assert codes(helper_before) == [(5, "W303")]


def test_w303_caught_and_match():
    caught = ("for o in records:\n    try:\n        o.write({'c': True})\n        if not o.email:\n"
              "            raise UserError('no email')\n    except UserError as e:\n        o.message_post(body=str(e))")
    assert codes(caught) == []
    match = "match record.state:\n    case 'draft':\n        record.write({'s': 1})\n    case 'cancel':\n        raise UserError('c')"
    assert codes(match) == []


def test_w303_is_linear():
    import time
    src = "for rec in records:\n    rec.write({'a': 1})\n" + "".join(
        f"    if rec.f{i} == {i}:\n        raise UserError('bad')\n" for i in range(2000))
    start = time.perf_counter()
    lint_code(src, "19.0")
    assert time.perf_counter() - start < 10


def test_batch_while_count_and_commit_in_helper():
    loop = ("domain = [('state', '=', 'draft')]\nwhile env['sale.order'].search_count(domain):\n"
            "    batch = env['sale.order'].search(domain, limit=500)\n    batch.action_cancel()\n    env.cr.commit()")
    assert codes(loop, caller="cron") == []
    helper = ("def process(batch):\n    batch.write({'d': True})\n    env.cr.commit()\n\nwhile True:\n"
              "    batch = model.search([('d', '=', False)], limit=200)\n    if not batch:\n        break\n    process(batch)")
    assert codes(helper, caller="cron") == []


def test_request_in_cron():
    assert codes("ip = request.httprequest.remote_addr", caller="cron") == [(1, "W210")]
    assert [d.code for d in lint_code("ip = request.httprequest.remote_addr", "19.0", "server_action",
                                      modules=frozenset({"website"}))] == []
