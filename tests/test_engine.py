import sys

import pytest

from sevlint.linter import lint_code


def codes(code, version="19.0", caller="server_action", **kw):
    return [(d.line, d.code) for d in lint_code(code, version, caller, **kw)]


def test_clean_code_has_no_findings():
    code = (
        "partners = env['res.partner'].search([('id', 'in', records.ids)])\n"
        "for p in partners:\n"
        "    p.write({'comment': 'x %s' % datetime.date.today()})\n"
        "action = {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'message': 'ok'}}\n"
    )
    assert codes(code) == []


def test_syntax_error_line():
    assert codes("x = 1\ny = (\n") == [(2, "E001")]


def test_indented_first_line_is_rejected_like_odoo():
    assert codes("    x = 1\n    y = 2")[0][1] == "E001"


def test_leading_blank_lines_shift_line_numbers():
    assert codes("\n\n\nimport os\n") == [(4, "E101")]


def test_forbidden_opcode_lines():
    code = "x = 1\nrecord.name = 'a'\nd = {}\ndel d['k']\n"
    assert codes(code) == [(2, "E101"), (4, "E101")]


def test_forbidden_name_is_reported_once_with_line():
    assert codes("a = 1\nb = record.__class__\n") == [(2, "E102")]


def test_dunder_string_literal_is_fine():
    assert codes("name = '__TEST__'") == []


def test_double_underscore_inside_identifier_is_forbidden():
    assert codes("temp__test = 1") == [(1, "E102")]


@pytest.mark.parametrize("name", ["type", "getattr", "hasattr", "print", "dir", "ValueError", "KeyError", "setattr"])
def test_undefined_builtins(name):
    assert codes(f"x = {name}") == [(1, "E201")]


@pytest.mark.parametrize("name", ["Exception", "isinstance", "reduce", "env", "model", "record", "records", "log",
                                  "_logger", "UserError", "Command", "float_compare", "b64encode", "timezone", "uid",
                                  "user", "datetime", "dateutil", "time", "xrange", "unicode"])
def test_defined_names(name):
    assert codes(f"x = {name}") == []


def test_locally_defined_names_are_known():
    assert codes("def helper(x):\n    return x\ny = helper(1)\nfor i in range(2):\n    z = i\nw = z") == []


def test_names_used_inside_functions_and_comprehensions():
    assert codes("def f():\n    return missing_a\nxs = [missing_b for _ in range(1)]") == [(2, "E201"), (3, "E201")]


def test_extra_names_option():
    assert codes("x = foo", names=frozenset({"foo"})) == []


def test_addon_names_warn_unless_module_declared():
    assert codes("x = json.dumps({})") == [(1, "W210")]
    assert codes("x = json.dumps({})", modules=frozenset({"base_automation"})) == []
    assert codes("x = request.httprequest", modules=frozenset({"website"})) == []


def test_wrapped_module_attributes():
    ok = "a = datetime.datetime.now()\nb = dateutil.relativedelta.relativedelta(days=1)\nc = time.strftime('%Y')\nd = dateutil.tz.gettz('UTC')"
    assert codes(ok) == []
    assert codes("t = time.mktime(x)") == [(1, "E201"), (1, "E202")]
    assert codes("e = dateutil.easter.easter(2026)") == [(1, "E202")]
    assert codes("e = dateutil.relativedelta.weekday") == [(1, "E202")]


def test_wrapped_module_shadowed_locally_is_not_checked():
    assert codes("time = 5\nx = time.real") == []


def test_inline_disable():
    assert codes("x = foo  # sevlint: disable=E201") == []
    assert codes("x = foo  # sevlint: disable") == []
    assert codes("x = foo  # sevlint: disable=W302") == [(1, "E201")]


def test_disabled_codes_and_wildcard():
    assert codes("x = foo", disabled=frozenset({"E201"})) == []
    loop = "for r in records:\n    env['x'].search([])"
    assert codes(loop) == [(2, "W302")]
    assert codes(loop, disabled=frozenset({"W*"})) == []


@pytest.mark.skipif(sys.version_info >= (3, 12), reason="PEP 709 inlines comprehensions on 3.12+")
def test_comprehension_closure_rejected_before_312():
    assert (2, "E101") in codes("def f(n):\n    return [i * n for i in range(3)]")


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 709 inlines comprehensions on 3.12+")
def test_comprehension_closure_accepted_since_312():
    assert codes("def f(n):\n    return [i * n for i in range(3)]") == []


def test_unknown_version():
    with pytest.raises(ValueError, match="unsupported Odoo version"):
        lint_code("x = 1", "12.0")


def test_huge_or_deep_code_does_not_crash():
    for code in ("x = " + "+".join(["1"] * 100000), "x = " + "-" * 200000 + "1", "f = " + "lambda: " * 1200 + "1"):
        found = codes(code)
        assert found and found[0][1] == "E001"


def test_wrapped_names_shadowed_in_nested_scopes():
    code = ("def fmt_slot(time):\n    return '%02d:%02d' % (time.hour, time.minute)\n"
            "hours = [time.hour for time in records.mapped('start')]\n"
            "f = lambda datetime: datetime.year\n"
            "def g():\n    dateutil = records[0].x\n    return dateutil.easter\n")
    assert codes(code) == []
    assert codes("def g():\n    return time.mktime(1)") == [(2, "E202")]


def test_closure_reported_on_function_lines_not_line_1():
    code = "x = 1\ny = 2\ndef outer(v):\n    return records.filtered(lambda r: r.x == v)\n"
    lines = {line for line, c in codes(code) if c == "E101"}
    assert lines and 1 not in lines and lines <= {3, 4}


def test_annotation_reported_on_its_line():
    assert {line for line, _ in codes("x = 1\n\ny: int = 2\n")} == {3}


def test_interpreter_flags_do_not_change_verdict(monkeypatch):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert codes("x = '\\d'\ny = x is 1") == []
    assert (1, "E101") in codes("assert records") or sys.version_info >= (3, 14)


def test_form_feed_does_not_shift_inline_disable():
    assert codes("x = 1\f\ny = foo  # sevlint: disable=E201") == []


def test_automation_implies_base_automation():
    assert codes("x = json.dumps({})", caller="automation") == []
    assert codes("x = payload", caller="cron", modules=frozenset({"base_automation"})) == [(1, "W210")]


def test_annotations_are_lazy_on_314():
    found = codes("def f(a: Missing) -> Missing2:\n    return a\nx = f(1)")
    if sys.version_info >= (3, 14):
        assert found == []
    else:
        assert [c for _, c in found] == ["E201", "E201"]


def test_module_annotation_line_ignores_function_annotations():
    code = "def compute(order):\n    total: float = 0.0\n    return total\n\nresult: dict = {}\n"
    assert {line for line, _ in codes(code)} == {5}


def test_hoisted_cell_of_inlined_comprehension_keeps_its_line():
    code = "partners = records.mapped('partner_id')\ngroups = [records.filtered(lambda r: r.partner_id == p) for p in partners]\n"
    assert {line for line, _ in codes(code)} == {2}
