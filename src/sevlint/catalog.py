"""Every rule: what it means and a failing and a fixed example (tests/test_catalog.py lints both).

This is the single source for `sevlint explain`, SARIF rule metadata and docs/rules.md
(`python tools/gen_docs.py` regenerates it; a test fails when it is stale).
"""
from __future__ import annotations

from dataclasses import dataclass, field

REPO = "https://github.com/Apoliak7777/new"
STAGES = {
    "save": "rejected when the action is saved",
    "install": "the module does not install",
    "runtime": "fails when the line runs",
    "future": "rejected after a server configuration change",
    "data": "data is lost or written differently than intended",
    "performance": "one query per record",
    "logic": "does something other than intended",
    "UX": "the user sees a traceback instead of a message",
}


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    title: str
    stage: str
    text: str
    bad: str
    good: str
    # how the examples are linted: odoo, caller, binding, model, modules, unsafe_policy, schema (live
    # database fields {model: [fields]} for sevlint remote rules); good_context overrides for `good`
    context: dict = field(default_factory=dict)
    good_context: dict = field(default_factory=dict)
    xml: bool = False  # the examples are XML data files

    @property
    def severity(self) -> str:
        return "error" if self.code.startswith("E") else "warning"

    @property
    def anchor(self) -> str:
        return self.code.lower()

    @property
    def help_uri(self) -> str:
        return f"{REPO}/blob/main/docs/rules.md#{self.anchor}"


def _xml(code: str) -> str:
    return ('<odoo>\n    <record id="action_demo" model="ir.actions.server">\n'
            '        <field name="name">Demo</field>\n'
            '        <field name="model_id" ref="sale.model_sale_order"/>\n'
            '        <field name="state">code</field>\n'
            f'        <field name="code">{code}</field>\n    </record>\n</odoo>\n')


RULES: list[Rule] = [
    Rule("E001", "syntax-error", "Syntax error, or code too long or deep for the compiler", "save",
         "Syntax error (or code too long/deep for the compiler). Odoo compiles `code.strip()` in exec "
         "mode: strip() removes only the first line's indentation, so an indented block is an "
         "IndentationError. Rejected when saving.",
         bad="    partners = records.mapped('partner_id')\n    partners.write({'comment': 'VIP'})\n",
         good="partners = records.mapped('partner_id')\npartners.write({'comment': 'VIP'})\n"),
    Rule("E003", "xml-child-element", "XML: an element inside the code field", "install",
         "XML: child element inside <field name=\"code\">. Odoo's import_xml.rng allows only text there, "
         "so the module fails to install.",
         bad=_xml("\nfor order in records:\n    order.message_post(body=\"<b>Checked</b>\")\n"),
         good=_xml("\nfor order in records:\n    order.message_post(body=\"&lt;b&gt;Checked&lt;/b&gt;\")\n"),
         xml=True),
    Rule("E004", "sandbox-refused", "Refused by the runtime sandbox (unsafe-policy raise)", "save",
         "Odoo 19.3+/20.0 with --unsafe-policy=raise/terminate: the runtime sandbox refuses bare "
         "`except:`, `async def` and async comprehensions. Rejected when saving.",
         bad="try:\n    records.action_confirm()\nexcept:\n    log('confirmation failed', level='warning')\n",
         good="try:\n    records.action_confirm()\nexcept Exception:\n    log('confirmation failed', level='warning')\n",
         context={"odoo": "saas-19.3", "unsafe_policy": "raise"}),
    Rule("E101", "forbidden-opcode", "Construct that safe_eval forbids (opcode)", "save",
         "Forbidden opcode. The construct compiles to bytecode outside Odoo's _SAFE_OPCODES "
         "(import, `obj.attr = x`, `del d[k]`, assert, with, class, closures, a, *b = ...). "
         "Depends on the Python version Odoo runs on. Rejected when saving.",
         bad="for partner in records:\n    partner.comment = 'VIP'\n",
         good="records.write({'comment': 'VIP'})\n"),
    Rule("E102", "forbidden-name", "Name or attribute that safe_eval forbids", "save",
         "Forbidden name. Any name/attribute containing '__' or listed in _UNSAFE_ATTRIBUTES "
         "(f_globals, mro, gi_frame, ...). String literals are NOT affected. Rejected when saving.",
         bad="model_name = record.__class__._name\n",
         good="model_name = record._name\n"),
    Rule("E201", "undefined-name", "Name that does not exist in the server action context", "runtime",
         "Undefined name. Not in the eval context, safe_eval builtins, or assigned in the code. "
         "Odoo does not check this on save; the action raises NameError when the line runs. "
         "Common cases: type, getattr, hasattr, print, ValueError, KeyError.",
         bad="if hasattr(record, 'email'):\n    log(record.email)\n",
         good="if 'email' in record._fields:\n    log(record.email)\n",
         context={"model": "res.partner"}),
    Rule("E202", "wrapped-module-attribute", "Attribute that Odoo's wrapped datetime/dateutil/time hide", "runtime",
         "Attribute not exposed by a wrapped module (datetime, dateutil, time). "
         "AttributeError at runtime, e.g. time.mktime or dateutil.easter.",
         bad="stamp = time.mktime(datetime.datetime.now().timetuple())\n",
         good="stamp = datetime.datetime.now().timestamp()\n"),
    Rule("E203", "renamed-field", "Field renamed in the target Odoo version", "runtime",
         "Field renamed between Odoo versions: the model has a similarly named field that appeared when this "
         "one disappeared (res.users groups_id -> group_ids in saas-18.2+, sale.order.line tax_id -> tax_ids). "
         "Checked where the model is known: env['model'], user, env.user/company, record/records with the "
         "action's model_id, and names assigned from those.",
         bad="admins = env['res.users'].search([('groups_id', 'in', env.ref('base.group_system').ids)])\n",
         good="admins = env['res.users'].search([('group_ids', 'in', env.ref('base.group_system').ids)])\n",
         context={"odoo": "19.0"}),
    Rule("E204", "missing-field-live", "Field that the live database does not have", "runtime",
         "sevlint remote: field the live database does not have. Judged in domains, rec['x'], "
         "mapped()/filtered()/sorted()/read() strings, write()/create() keys that are x_ names or fields of some "
         "Odoo version, and rec.x when x is an x_ name or a field of some Odoo version (other names may be "
         "methods). Typical: a Studio field recreated as x_field_1.",
         bad="records.write({'x_studio_tier': 'gold'})\n",
         good="records.write({'x_studio_tier_1': 'gold'})\n",
         context={"model": "res.partner", "schema": {"res.partner": ["name", "x_studio_tier_1"]}}),
    Rule("E205", "missing-model-live", "Model that is not installed in the live database", "runtime",
         "sevlint remote: env['model'] for a model not installed in the live database (KeyError). Not "
         "reported when guarded by `'model' in env` or inside try:.",
         bad="vehicles = env['x_fleet.vehicle'].search([])\n",
         good="if 'x_fleet.vehicle' in env:\n    vehicles = env['x_fleet.vehicle'].search([])\n",
         context={"model": "res.partner", "schema": {"res.partner": ["name"]}}),
    Rule("W100", "xml-dropped-text", "XML: code after a comment is dropped", "data",
         "XML: text after a comment or child element inside <field name=\"code\"> is dropped by Odoo "
         "(it stores node.text only).",
         bad=_xml("\nrecords.action_confirm()\n<!-- then notify the salesperson -->\n"
                  "records.message_post(body='Confirmed')\n"),
         good=_xml("\nrecords.action_confirm()\n# then notify the salesperson\n"
                   "records.message_post(body='Confirmed')\n"),
         xml=True),
    Rule("W110", "python-dependent", "Accepted or rejected depending on the server's Python", "save",
         "The verdict depends on the Python the Odoo server runs: comprehension closures and `(*a, b)` are "
         "rejected before 3.12, `@` on 3.10, `assert` before 3.14, newer syntax where it does not exist. Silenced "
         "when target-python pins the server's Python (then the verdict is exact).",
         bad="def labels(partners, prefix):\n    return [prefix + p.name for p in partners]\n\n"
             "log(', '.join(labels(records, 'VIP ')))\n",
         good="def labels(partners, prefix):\n    out = []\n    for p in partners:\n        out.append(prefix + p.name)\n"
              "    return out\n\nlog(', '.join(labels(records, 'VIP ')))\n",
         context={"odoo": "19.0"}),
    Rule("W203", "removed-field", "Field that the target version's Community does not have", "runtime",
         "Field not in the target version's Odoo Community (it is in another version) and no obvious rename: "
         "removed, or moved to an Enterprise/custom module.",
         bad="lead = env['crm.lead'].browse(record.id)\nnumber = lead.mobile\n",
         good="lead = env['crm.lead'].browse(record.id)\nnumber = lead.phone\n",
         context={"odoo": "19.0"}),
    Rule("W204", "unknown-vals-key-live", "write()/create() key that is not a field of the live database", "runtime",
         "sevlint remote: write()/create() key that is not a field of the live database's model: ValueError "
         "(Invalid field) unless the model's create()/write() override consumes the key.",
         bad="records.write({'is_vip': True})\n",
         good="records.write({'x_studio_is_vip': True})\n",
         context={"model": "res.partner", "schema": {"res.partner": ["name", "x_studio_is_vip"]}}),
    Rule("W205", "removed-model", "Model that the target version's Community does not have", "runtime",
         "Model not in the target version's Odoo Community (it is in another version).",
         bad="layers = env['stock.valuation.layer'].search([('product_id', '=', record.id)])\n",
         good="moves = env['stock.move'].search([('product_id', '=', record.id), ('state', '=', 'done')])\n",
         context={"odoo": "19.0"}),
    Rule("W210", "addon-name", "Name that only an addon provides", "runtime",
         "Name provided only by an addon (json: base_automation/website, request: website, "
         "payload: base_automation + an HTTP request, never in scheduled runs). Declare installed modules "
         "with --modules or config. `request` in a scheduled action is an unbound proxy.",
         bad="record.message_post(body=json.dumps({'id': record.id}))\n",
         good="record.message_post(body=json.dumps({'id': record.id}))\n",
         good_context={"modules": ["base_automation"]}),
    Rule("W220", "sandbox-logged", "Logged by the runtime sandbox, refused under unsafe-policy raise", "future",
         "Odoo 19.3+/20.0 with the default --unsafe-policy=log: bare `except:` / async code is logged by the "
         "sandbox and rejected once the server runs with --unsafe-policy=raise. Use `except Exception:`.",
         bad="try:\n    records.action_confirm()\nexcept:\n    log('confirmation failed', level='warning')\n",
         good="try:\n    records.action_confirm()\nexcept Exception:\n    log('confirmation failed', level='warning')\n",
         context={"odoo": "saas-19.3"}),
    Rule("W301", "commit", "env.cr.commit() or rollback() in a server action", "data",
         "env.cr.commit()/rollback() inside a server action: breaks atomicity of the action. "
         "Commits inside a loop of a scheduled action (batching) are not reported.",
         bad="records.write({'comment': 'exported'})\nenv.cr.commit()\n",
         good="records.write({'comment': 'exported'})\n"),
    Rule("W302", "query-in-loop", "Query per record (N+1)", "performance",
         "ORM query method (search, search_count, read_group, ...) inside a loop, a per-record lambda "
         "(filtered/mapped/sorted) or a helper called from one: one query per iteration. "
         "`search(..., limit=N)` in a while loop (batching) is not reported.",
         bad="for order in records:\n"
             "    n = env['sale.order.line'].search_count([('order_id', '=', order.id)])\n"
             "    order.message_post(body=str(n))\n",
         good="lines = env['sale.order.line'].search([('order_id', 'in', records.ids)])\n"
              "for order in records:\n"
              "    n = len(lines.filtered(lambda line: line.order_id == order))\n"
              "    order.message_post(body=str(n))\n",
         context={"model": "sale.order"}),
    Rule("W303", "rolled-back-write", "UserError after a write rolls the write back", "data",
         "raise UserError after write/create/unlink on the same path: the exception rolls the transaction "
         "back. Fine for an intentional dry run (disable with `# sevlint: disable=W303`).",
         bad="records.write({'note': 'checked'})\n"
             "if any(order.amount_total > 10000 for order in records):\n"
             "    raise UserError('Orders above 10 000 need approval')\n",
         good="if any(order.amount_total > 10000 for order in records):\n"
              "    raise UserError('Orders above 10 000 need approval')\n"
              "records.write({'note': 'checked'})\n",
         context={"model": "sale.order"}),
    Rule("W304", "record-in-cron", "record/records in a scheduled action", "runtime",
         "record/records in a scheduled action (ir.cron): both are None there.",
         bad="for order in records:\n    order.action_confirm()\n",
         good="for order in model.search([('state', '=', 'draft')]):\n    order.action_confirm()\n",
         context={"caller": "cron", "model": "sale.order"}),
    Rule("W305", "first-record-only", "record in an action offered for a selection", "logic",
         "`record` without `records` in an action offered in list views (or kanban views on 19.0+): "
         "the code runs once, `record` is the first selected record, the rest is ignored.",
         bad="record.action_confirm()\n",
         good="records.action_confirm()\n",
         context={"binding": "list,form", "model": "sale.order"}),
    Rule("W306", "raise-exception", "raise Exception shows a traceback", "UX",
         "raise Exception(...): safe_eval re-raises it as ValueError, the user sees a server error "
         "with traceback. Raise UserError for a message.",
         bad="if not record.partner_id:\n    raise Exception('Set a customer first')\n",
         good="if not record.partner_id:\n    raise UserError('Set a customer first')\n",
         context={"model": "sale.order"}),
]
BY_CODE = {rule.code: rule for rule in RULES}


def explain(rule: Rule) -> str:
    fence = "xml" if rule.xml else "python"
    out = [f"{rule.code} {rule.name}: {rule.title} ({STAGES[rule.stage]})", "", rule.text, "",
           f"Bad:\n```{fence}\n{rule.bad.rstrip()}\n```", f"Good:\n```{fence}\n{rule.good.rstrip()}\n```"]
    context = {k: v for k, v in rule.context.items() if k != "schema"}
    if context or rule.good_context:
        out.append("Linted with: " + ", ".join(f"{k}={v}" for k, v in context.items())
                   + (f"; the good example with {rule.good_context}" if rule.good_context else ""))
    return "\n".join(out)


def markdown() -> str:
    lines = ["# sevlint rules", "",
             "Generated from `src/sevlint/catalog.py` by `python tools/gen_docs.py`; every example below is "
             "linted by the test suite (the bad one must report the rule, the good one must be clean).", "",
             "| Code | Name | Stage | Summary |", "| --- | --- | --- | --- |"]
    lines += [f"| [{r.code}](#{r.anchor}) | `{r.name}` | {r.stage} | {r.title} |" for r in RULES]
    for rule in RULES:
        fence = "xml" if rule.xml else "python"
        lines += ["", f"## {rule.code}", "", f"**{rule.title}** (`{rule.name}`, {rule.severity}: "
                  f"{STAGES[rule.stage]})", "", rule.text, "", "Bad:", "", f"```{fence}", rule.bad.rstrip(), "```",
                  "", "Good:", "", f"```{fence}", rule.good.rstrip(), "```"]
        context = {k: v for k, v in rule.context.items() if k != "schema"}
        notes = []
        if context:
            notes.append(", ".join(f"`{k}={v}`" for k, v in context.items()))
        if "schema" in rule.context:
            notes.append("`sevlint remote` against a database whose fields are "
                         + "; ".join(f"`{m}`: {', '.join(fs)}" for m, fs in rule.context["schema"].items()))
        if rule.good_context:
            notes.append("the good example with " + ", ".join(f"`{k}={','.join(v)}`" for k, v in rule.good_context.items()))
        if notes:
            lines += ["", "Linted with " + "; ".join(notes) + "."]
    return "\n".join(lines) + "\n"
