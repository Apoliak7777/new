import ast
import json
import sys
import types
import xmlrpc.client

import pytest

from sevlint import cli, fields, remote
from mock_odoo import API_KEY, DB, LOGIN, MockOdoo, action, modules, schema

ORIGINAL_INIT = remote.Transport.__init__
PARTNER = ["name", "email", "is_company", "x_studio_tier_1", "user_id", "active"]
USERS = ["name", "login", "group_ids", "partner_id"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for var in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(var, "127.0.0.1,localhost")
    monkeypatch.setenv("ODOO_API_KEY", API_KEY)
    monkeypatch.setitem(sys.modules, "keyring", None)  # no keyring unless a test installs a fake one
    monkeypatch.setattr(remote.Transport, "__init__", _fast_transport(remote.Transport.__init__))


def _fast_transport(init):
    def patched(self, base, *, timeout=30.0, min_interval=None, opener=None):
        init(self, base, timeout=5.0, min_interval=0.0 if min_interval is None else min_interval, opener=opener)
    return patched


def tables(actions, installed=("base_automation",), crons=(), automations=(), models=None):
    rows = [dict(a) for a in actions]
    if "base_automation" not in installed:
        for row in rows:
            row.pop("base_automation_id")
    out = {
        "ir.module.module": modules(*installed),
        "ir.actions.server": rows,
        "ir.cron": list(crons) or [{"id": 999, "ir_actions_server_id": False, "active": True}],
        **schema(models if models is not None else {"res.partner": PARTNER, "res.users": USERS}),
    }
    if "base_automation" in installed:
        out["base.automation"] = list(automations) or [{"id": 999, "active": True, "trigger": "on_create"}]
    return out


def run(argv, capsys):
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


ACTIONS = [
    action(1, "for rec in records:\n    rec.write({'x_studio_tier': 'gold'})\n", name="Set tier",
           binding_model_id=[80, "Contact"], xml_id="__export__.ir_act_server_1_abc"),
    action(2, "env['x_fleet.vehicle'].search([])\n", name="Missing model"),
    action(3, "partners = model.search([('is_company', '=', True)])\nlog(str(len(partners)))\n",
           name="Nightly", usage="ir_cron"),
    action(4, "record.message_post(body=str(payload))\n", name="Webhook", usage="base_automation",
           base_automation_id=[7, "Webhook rule"]),
    action(5, "records.write({'email': False})\n", name="Clean", state="object_write"),
    action(6, "", name="Empty"),
    action(7, "x = record.x_studio_tier_1\nrecord.action_archive()\n", name="Fine"),
]


def test_json2_end_to_end(capsys):
    with MockOdoo("19.0", enterprise=True, tables=tables(ACTIONS)) as odoo:
        code, out, err = run(["remote", odoo.url, "--db", DB], capsys)
    assert code == 1
    lines = out.splitlines()
    assert any(l.startswith("ir.actions.server/1:2: E204 field `x_studio_tier` does not exist on `res.partner`")
               and "similar: `x_studio_tier_1`" in l and "'Set tier' __export__.ir_act_server_1_abc" in l
               for l in lines), out
    assert any(l.startswith("ir.actions.server/2:1: E205 model `x_fleet.vehicle` is not installed") for l in lines)
    assert not any(l.startswith(("ir.actions.server/3:", "ir.actions.server/4:", "ir.actions.server/7:"))
                   for l in lines), out  # cron without record, webhook payload, Studio field + method
    assert not any("/5:" in l or "/6:" in l for l in lines)  # not code / empty
    assert "Odoo 19.0+e (Enterprise), 5 code action(s) read via JSON-2" in err
    assert "2 error(s), 0 warning(s) in 5 action(s)" in err
    assert API_KEY not in out + err
    orm_calls = [r for r in odoo.requests if r["path"].startswith("/json/2/")]
    assert {r["path"].rsplit("/", 1)[-1] for r in orm_calls} == {"search_read"}
    assert all(r["headers"]["Authorization"] == f"bearer {API_KEY}" for r in orm_calls)
    assert all(r["headers"]["X-Odoo-Database"] == DB for r in orm_calls)
    version_call = next(r for r in odoo.requests if r["path"] == "/web/webclient/version_info")
    assert "Authorization" not in version_call["headers"]
    fields_call = json.loads(next(r for r in orm_calls if r["path"].endswith("/ir.model.fields/search_read"))["body"])
    assert fields_call["domain"] == [["model", "in", ["res.partner"]]]


def test_cron_record_and_labels(capsys):
    acts = [action(3, "record.write({'name': 'x'})\n", name="Cron", usage="ir_cron")]
    crons = [{"id": 1, "ir_actions_server_id": [3, "Cron"], "active": False}]
    with MockOdoo("saas~19.2", tables=tables(acts, crons=crons)) as odoo:
        code, out, err = run(["remote", odoo.url, "--format", "json"], capsys)
    data = json.loads(out)
    (finding,) = data["findings"]
    assert finding["code"] == "W304" and finding["caller"] == "cron" and finding["odoo_version"] == "saas-19.2"
    assert finding["label"] == "'Cron' (archived)"
    assert code == 0


def test_xmlrpc_end_to_end_17(capsys):
    acts = [action(1, "users = env['res.users'].search([('groups_id', '!=', False)])\n"
                      "x = type(users)\n")]
    models = {"res.users": ["name", "login", "groups_id", "partner_id"]}
    with MockOdoo("17.0", tables=tables(acts, installed=(), models=models)) as odoo:
        code, out, err = run(["remote", odoo.url, "--db", DB, "--user", LOGIN], capsys)
    assert code == 1
    (line,) = out.strip().splitlines()
    assert line.startswith("ir.actions.server/1:2: E201 name `type` is not defined") and "[17.0 server_action" in line
    assert "read via XML-RPC" in err and API_KEY not in out + err
    assert not any(r["path"].startswith("/json/2/") for r in odoo.requests)
    calls = [xmlrpc.client.loads(r["body"])[0] for r in odoo.requests if r["path"] == "/xmlrpc/2/object"]
    assert {(c[3], c[4]) for c in calls} == {("ir.module.module", "search_read"), ("ir.actions.server", "search_read"),
                                            ("ir.cron", "search_read"), ("ir.model", "search_read"),
                                            ("ir.model.fields", "search_read")}  # no base.automation: not installed


def test_xmlrpc_requires_db_and_user(capsys):
    with MockOdoo("18.0", tables=tables([])) as odoo:
        code, _, err = run(["remote", odoo.url], capsys)
    assert code == 2 and "needs --db and --user" in err


def test_json2_missing_on_18(capsys):
    with MockOdoo("18.0", tables=tables([])) as odoo:
        code, _, err = run(["remote", odoo.url, "--protocol", "json2"], capsys)
    assert code == 2 and "no JSON-2 endpoint" in err and "--protocol xmlrpc" in err


def test_wrong_key_is_not_echoed(capsys, monkeypatch):
    monkeypatch.setenv("ODOO_API_KEY", "f" * 40)
    with MockOdoo("19.0", tables=tables([])) as odoo:
        code, out, err = run(["remote", odoo.url], capsys)
    assert code == 2 and "authentication failed" in err
    assert "f" * 40 not in out + err


def test_xmlrpc_wrong_key(capsys, monkeypatch):
    monkeypatch.setenv("ODOO_API_KEY", "e" * 40)
    with MockOdoo("17.0", tables=tables([])) as odoo:
        code, out, err = run(["remote", odoo.url, "--db", DB, "--user", LOGIN], capsys)
    assert code == 2 and "authentication failed" in err and "e" * 40 not in out + err


def test_no_key(capsys, monkeypatch):
    monkeypatch.delenv("ODOO_API_KEY")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    with MockOdoo("19.0", tables=tables([])) as odoo:
        code, _, err = run(["remote", odoo.url], capsys)
    assert code == 2 and "no API key: set ODOO_API_KEY" in err
    assert not any(r["path"].startswith("/json/2/") for r in odoo.requests)


def test_custom_env_var_and_keyring(capsys, monkeypatch):
    monkeypatch.delenv("ODOO_API_KEY")
    monkeypatch.setenv("MY_KEY", API_KEY)
    with MockOdoo("19.0", tables=tables([])) as odoo:
        assert run(["remote", odoo.url, "--api-key-env", "MY_KEY"], capsys)[0] == 0
        fake = types.SimpleNamespace(get_password=lambda service, host: API_KEY if (service, host) == (
            "sevlint", "127.0.0.1") else None)
        monkeypatch.setitem(sys.modules, "keyring", fake)
        assert run(["remote", odoo.url], capsys)[0] == 0


def test_keyring_backend_error_falls_through(monkeypatch):
    monkeypatch.delenv("ODOO_API_KEY")

    def broken(*_):
        raise RuntimeError("no backend")
    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_password=broken))
    with pytest.raises(remote.RemoteError, match="no API key"):
        remote.api_key("ODOO_API_KEY", "h", interactive=False)
    monkeypatch.setattr(remote.getpass, "getpass", lambda prompt: " typed ")
    assert remote.api_key("ODOO_API_KEY", "h", interactive=True) == "typed"


def test_unsupported_version_before_key(capsys, monkeypatch):
    monkeypatch.delenv("ODOO_API_KEY")
    with MockOdoo("16.0", tables=tables([])) as odoo:
        code, _, err = run(["remote", odoo.url], capsys)
    assert code == 2 and "unsupported Odoo version '16.0'" in err and "API key" not in err


def test_not_odoo(capsys):
    with MockOdoo("19.0") as odoo:
        odoo.html_everywhere = True
        code, _, err = run(["remote", odoo.url], capsys)
    assert code == 2 and "does not answer like an Odoo server" in err


def test_redirect_refused_and_credentials_not_forwarded(capsys):
    with MockOdoo("19.0", tables=tables([])) as odoo:
        odoo.redirect["/json/2/ir.module.module/search_read"] = odoo.url + "/elsewhere"
        code, _, err = run(["remote", odoo.url], capsys)
    assert code == 2 and "redirects to" in err
    assert not any(r["path"] == "/elsewhere" for r in odoo.requests)


def test_retry_after_429(capsys):
    with MockOdoo("19.0", tables=tables([action(1, "x = 1\n")])) as odoo:
        odoo.fail_once["/json/2/ir.module.module/search_read"] = (429, {"Retry-After": "0"})
        code, _, err = run(["remote", odoo.url], capsys)
    assert code == 0 and "1 code action(s)" in err
    assert sum(r["path"] == "/json/2/ir.module.module/search_read" for r in odoo.requests) == 2


def test_pagination(capsys, monkeypatch):
    monkeypatch.setattr(remote, "PAGE", 2)
    acts = [action(i, f"x = {i}\n") for i in range(1, 6)]
    with MockOdoo("19.0", tables=tables(acts)) as odoo:
        code, _, err = run(["remote", odoo.url], capsys)
    assert code == 0 and "5 code action(s)" in err
    assert sum(r["path"] == "/json/2/ir.actions.server/search_read" for r in odoo.requests) == 3


def test_ids_and_only(capsys):
    with MockOdoo("19.0", tables=tables(ACTIONS)) as odoo:
        code, out, err = run(["remote", odoo.url, "--ids", "2,3"], capsys)
        assert "2 code action(s)" in err and "E205" in out and "E204" not in out
        code, out, err = run(["remote", odoo.url, "--only", "cron"], capsys)
        assert code == 0 and "1 code action(s)" in err
        code, _, err = run(["remote", odoo.url, "--only", "bogus"], capsys)
        assert code == 2
        code, _, err = run(["remote", odoo.url, "--ids", "a,b"], capsys)
        assert code == 2 and "--ids" in err


def test_upgrade_check_uses_index(capsys):
    acts = [action(1, "admins = env['res.users'].search([('groups_id', '!=', False)])\n", model="res.users")]
    models = {"res.users": ["name", "login", "groups_id"]}
    with MockOdoo("18.0", tables=tables(acts, installed=(), models=models)) as odoo:
        code, out, err = run(["remote", odoo.url, "--db", DB, "--user", LOGIN, "--odoo", "19.0"], capsys)
        paths = [r["body"] for r in odoo.requests if r["path"] == "/xmlrpc/2/object"]
    assert code == 1 and "E203 field `groups_id` was renamed" in out and "use `group_ids`" in out
    assert "linted as Odoo 19.0 (the database runs 18.0)" in err
    assert not any(b"ir.model.fields" in body for body in paths)


def test_no_schema_uses_index(capsys):
    with MockOdoo("19.0", tables=tables(ACTIONS)) as odoo:
        code, out, err = run(["remote", odoo.url, "--no-schema"], capsys)
        assert not any("ir.model.fields" in r["path"] for r in odoo.requests)
    assert "E204" not in out and "E205" not in out and "bundled index (--no-schema)" in err


def test_dump_round_trip(tmp_path, capsys, monkeypatch):
    with MockOdoo("19.0", tables=tables(ACTIONS)) as odoo:
        run(["remote", odoo.url, "--dump", str(tmp_path / "dump")], capsys)
    files = sorted(p.name for p in (tmp_path / "dump").iterdir())
    assert files == ["1_set_tier.py", "2_missing_model.py", "3_nightly.py", "4_webhook.py", "7_fine.py"]
    text = (tmp_path / "dump" / "1_set_tier.py").read_text()
    assert text.splitlines()[:2] == [
        "# ir.actions.server/1 'Set tier' __export__.ir_act_server_1_abc",
        "# sevlint: odoo=19.0 caller=server_action model=res.partner modules=base_automation binding=list,form"]
    monkeypatch.chdir(tmp_path)
    code, out, err = run(["check", "dump"], capsys)
    assert code == 0, out + err  # offline: Studio/custom names are not judged
    assert "5 snippet(s) from 5 file(s)" in err


def test_read_only_guard():
    client = remote.Json2Client(remote.Transport("http://127.0.0.1:9"), None, API_KEY)
    with pytest.raises(remote.RemoteError, match="only reads"):
        client.call("res.partner", "write", ids=[1], vals={})


@pytest.mark.parametrize("url, expected", [
    ("mycompany.odoo.com", "https://mycompany.odoo.com"),
    ("https://mycompany.odoo.com/", "https://mycompany.odoo.com"),
    ("http://localhost:8069", "http://localhost:8069"),
    ("https://mycompany.odoo.com/odoo/action-12?debug=1#x", "https://mycompany.odoo.com"),  # copied from the browser
    ("http://[::1]:8069/web", "http://[::1]:8069"),
])
def test_parse_url(url, expected):
    assert remote.parse_url(url) == expected


@pytest.mark.parametrize("url, message", [
    ("http://erp.example.com", "plain http"),
    ("https://admin:secret@erp.example.com", "credentials in the URL"),
    ("ftp://erp.example.com", "not an http"),
])
def test_parse_url_refuses(url, message):
    with pytest.raises(remote.RemoteError, match=message):
        remote.parse_url(url)
    assert remote.parse_url("http://erp.example.com", allow_http=True) == "http://erp.example.com"


def test_unreachable_is_exit_2(capsys):
    code, _, err = run(["remote", "http://127.0.0.1:9"], capsys)
    assert code == 2 and "cannot reach" in err


def test_redact():
    transport = remote.Transport("https://x.odoo.com")
    transport.secret = "abc"
    assert transport.redact("key abc leaked") == "key *** leaked"


def test_default_interval_for_odoo_online():
    def interval(url):
        transport = remote.Transport.__new__(remote.Transport)
        ORIGINAL_INIT(transport, url)
        return transport.min_interval
    assert interval("https://x.odoo.com") == 1.0
    assert interval("https://erp.example.com") == 0.0


# -- live field checks ------------------------------------------------------------------

def _live(code, model="res.partner", version="19.0", live=None):
    live = live or fields.LiveSchema(frozenset({"res.partner", "res.users"}),
                                     {"res.partner": frozenset(PARTNER), "res.users": frozenset(USERS)})
    return [(d.line, d.code, d.message) for d in fields.check_live_fields(ast.parse(code), version, model, live)]


def test_live_attribute_needs_field_evidence():
    assert _live("record.action_confirm()\nrecord.name\n") == []  # a method, a present field
    (diag,) = _live("x = record.x_studio_tier\n")
    assert diag[:2] == (1, "E204") and "similar: `x_studio_tier_1`" in diag[2] and "AttributeError" in diag[2]


def test_live_field_contexts():
    code = ("records.write({'x_nope': 1})\n"
            "env['res.partner'].search([('bogus.id', '=', 1), '|', ('name', '=', 'a'), ('email', '=', 'b')])\n"
            "records.sorted('mystery desc, id')\n"
            "records.mapped('ghost.name')\n"
            "record['phantom']\n"
            "env['res.partner'].create([{'mobile': 1}])\n")  # a field in other versions: renamed/removed
    assert [(line, code) for line, code, _ in _live(code)] == [
        (1, "E204"), (2, "E204"), (3, "E204"), (4, "E204"), (5, "E204"), (6, "E204")]


def test_live_unknown_vals_key_is_a_warning():
    # create()/write() overrides may pop extra keys (account.bank.statement.line: counterpart_account_id)
    ((line, code, message),) = _live("records.write({'counterpart_account_id': 1})\n")
    assert (line, code) == (1, "W204") and "unless the model's create()/write() consumes this key" in message


def test_live_rename_hint_from_index():
    (diag,) = _live("user.groups_id\n", model=None)
    assert "renamed, use `group_ids`" in diag[2]


def test_live_models_guarded():
    assert _live("if 'x_fleet.vehicle' in env:\n    env['x_fleet.vehicle'].search([])\n") == []
    assert _live("try:\n    env['x_fleet.vehicle']\nexcept Exception:\n    pass\n") == []
    assert [c for _, c, _ in _live("env['x_fleet.vehicle']\n")] == ["E205"]


def test_live_unknown_model_fields_not_judged():
    assert _live("env['sale.order'].search([('whatever', '=', 1)])\n",
                 live=fields.LiveSchema(frozenset({"res.partner", "sale.order"}), {})) == []


def test_referenced_models():
    tree = ast.parse("u = env.user\nu.login\nenv['sale.order'].search([])\n")
    assert fields.referenced_models(tree, "res.partner") == {"res.users", "sale.order", "res.partner"}


def test_cli_constants_match_remote():
    assert (cli.DEFAULT_KEY_ENV, cli.PROTOCOLS) == (remote.DEFAULT_KEY_ENV, remote.PROTOCOLS)


def test_natural_order_of_actions(capsys):
    acts = [action(i, "x = type(1)\n") for i in (2, 10, 9)]
    with MockOdoo("19.0", tables=tables(acts)) as odoo:
        _, out, _ = run(["remote", odoo.url], capsys)
    assert [l.split(":")[0] for l in out.splitlines()] == [
        "ir.actions.server/2", "ir.actions.server/9", "ir.actions.server/10"]


def test_wrong_db_and_access_denied(capsys):
    with MockOdoo("19.0", tables=tables([])) as odoo:
        code, _, err = run(["remote", odoo.url, "--db", "other"], capsys)
        assert code == 2 and "for database 'other'" in err and "check --db" in err
    client = remote.Json2Client(remote.Transport("http://127.0.0.1:9"), None, API_KEY)
    client.transport.post = lambda *a: (403, "application/json", b'{"message": "You are not allowed"}')
    with pytest.raises(remote.RemoteError, match="access denied .You are not allowed.; the API key's user needs "
                                                 "Administration / Settings"):
        client.search_read("ir.actions.server", [], ["name"])
