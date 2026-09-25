# sevlint rules

Generated from `src/sevlint/catalog.py` by `python tools/gen_docs.py`; every example below is linted by the test suite (the bad one must report the rule, the good one must be clean).

| Code | Name | Stage | Summary |
| --- | --- | --- | --- |
| [E001](#e001) | `syntax-error` | save | Syntax error, or code too long or deep for the compiler |
| [E003](#e003) | `xml-child-element` | install | XML: an element inside the code field |
| [E004](#e004) | `sandbox-refused` | save | Refused by the runtime sandbox (unsafe-policy raise) |
| [E101](#e101) | `forbidden-opcode` | save | Construct that safe_eval forbids (opcode) |
| [E102](#e102) | `forbidden-name` | save | Name or attribute that safe_eval forbids |
| [E201](#e201) | `undefined-name` | runtime | Name that does not exist in the server action context |
| [E202](#e202) | `wrapped-module-attribute` | runtime | Attribute that Odoo's wrapped datetime/dateutil/time hide |
| [E203](#e203) | `renamed-field` | runtime | Field renamed in the target Odoo version |
| [E204](#e204) | `missing-field-live` | runtime | Field that the live database does not have |
| [E205](#e205) | `missing-model-live` | runtime | Model that is not installed in the live database |
| [W100](#w100) | `xml-dropped-text` | data | XML: code after a comment is dropped |
| [W110](#w110) | `python-dependent` | save | Accepted or rejected depending on the server's Python |
| [W203](#w203) | `removed-field` | runtime | Field that the target version's Community does not have |
| [W204](#w204) | `unknown-vals-key-live` | runtime | write()/create() key that is not a field of the live database |
| [W205](#w205) | `removed-model` | runtime | Model that the target version's Community does not have |
| [W210](#w210) | `addon-name` | runtime | Name that only an addon provides |
| [W220](#w220) | `sandbox-logged` | future | Logged by the runtime sandbox, refused under unsafe-policy raise |
| [W301](#w301) | `commit` | data | env.cr.commit() or rollback() in a server action |
| [W302](#w302) | `query-in-loop` | performance | Query per record (N+1) |
| [W303](#w303) | `rolled-back-write` | data | UserError after a write rolls the write back |
| [W304](#w304) | `record-in-cron` | runtime | record/records in a scheduled action |
| [W305](#w305) | `first-record-only` | logic | record in an action offered for a selection |
| [W306](#w306) | `raise-exception` | UX | raise Exception shows a traceback |

## E001

**Syntax error, or code too long or deep for the compiler** (`syntax-error`, error: rejected when the action is saved)

Syntax error (or code too long/deep for the compiler). Odoo compiles `code.strip()` in exec mode: strip() removes only the first line's indentation, so an indented block is an IndentationError. Rejected when saving.

Bad:

```python
    partners = records.mapped('partner_id')
    partners.write({'comment': 'VIP'})
```

Good:

```python
partners = records.mapped('partner_id')
partners.write({'comment': 'VIP'})
```

## E003

**XML: an element inside the code field** (`xml-child-element`, error: the module does not install)

XML: child element inside <field name="code">. Odoo's import_xml.rng allows only text there, so the module fails to install.

Bad:

```xml
<odoo>
    <record id="action_demo" model="ir.actions.server">
        <field name="name">Demo</field>
        <field name="model_id" ref="sale.model_sale_order"/>
        <field name="state">code</field>
        <field name="code">
for order in records:
    order.message_post(body="<b>Checked</b>")
</field>
    </record>
</odoo>
```

Good:

```xml
<odoo>
    <record id="action_demo" model="ir.actions.server">
        <field name="name">Demo</field>
        <field name="model_id" ref="sale.model_sale_order"/>
        <field name="state">code</field>
        <field name="code">
for order in records:
    order.message_post(body="&lt;b&gt;Checked&lt;/b&gt;")
</field>
    </record>
</odoo>
```

## E004

**Refused by the runtime sandbox (unsafe-policy raise)** (`sandbox-refused`, error: rejected when the action is saved)

Odoo 19.3+/20.0 with --unsafe-policy=raise/terminate: the runtime sandbox refuses bare `except:`, `async def` and async comprehensions. Rejected when saving.

Bad:

```python
try:
    records.action_confirm()
except:
    log('confirmation failed', level='warning')
```

Good:

```python
try:
    records.action_confirm()
except Exception:
    log('confirmation failed', level='warning')
```

Linted with `odoo=saas-19.3`, `unsafe_policy=raise`.

## E101

**Construct that safe_eval forbids (opcode)** (`forbidden-opcode`, error: rejected when the action is saved)

Forbidden opcode. The construct compiles to bytecode outside Odoo's _SAFE_OPCODES (import, `obj.attr = x`, `del d[k]`, assert, with, class, closures, a, *b = ...). Depends on the Python version Odoo runs on. Rejected when saving.

Bad:

```python
for partner in records:
    partner.comment = 'VIP'
```

Good:

```python
records.write({'comment': 'VIP'})
```

## E102

**Name or attribute that safe_eval forbids** (`forbidden-name`, error: rejected when the action is saved)

Forbidden name. Any name/attribute containing '__' or listed in _UNSAFE_ATTRIBUTES (f_globals, mro, gi_frame, ...). String literals are NOT affected. Rejected when saving.

Bad:

```python
model_name = record.__class__._name
```

Good:

```python
model_name = record._name
```

## E201

**Name that does not exist in the server action context** (`undefined-name`, error: fails when the line runs)

Undefined name. Not in the eval context, safe_eval builtins, or assigned in the code. Odoo does not check this on save; the action raises NameError when the line runs. Common cases: type, getattr, hasattr, print, ValueError, KeyError.

Bad:

```python
if hasattr(record, 'email'):
    log(record.email)
```

Good:

```python
if 'email' in record._fields:
    log(record.email)
```

Linted with `model=res.partner`.

## E202

**Attribute that Odoo's wrapped datetime/dateutil/time hide** (`wrapped-module-attribute`, error: fails when the line runs)

Attribute not exposed by a wrapped module (datetime, dateutil, time). AttributeError at runtime, e.g. time.mktime or dateutil.easter.

Bad:

```python
stamp = time.mktime(datetime.datetime.now().timetuple())
```

Good:

```python
stamp = datetime.datetime.now().timestamp()
```

## E203

**Field renamed in the target Odoo version** (`renamed-field`, error: fails when the line runs)

Field renamed between Odoo versions: the model has a similarly named field that appeared when this one disappeared (res.users groups_id -> group_ids in saas-18.2+, sale.order.line tax_id -> tax_ids). Checked where the model is known: env['model'], user, env.user/company, record/records with the action's model_id, and names assigned from those.

Bad:

```python
admins = env['res.users'].search([('groups_id', 'in', env.ref('base.group_system').ids)])
```

Good:

```python
admins = env['res.users'].search([('group_ids', 'in', env.ref('base.group_system').ids)])
```

Linted with `odoo=19.0`.

## E204

**Field that the live database does not have** (`missing-field-live`, error: fails when the line runs)

sevlint remote: field the live database does not have. Judged in domains, rec['x'], mapped()/filtered()/sorted()/read() strings, write()/create() keys that are x_ names or fields of some Odoo version, and rec.x when x is an x_ name or a field of some Odoo version (other names may be methods). Typical: a Studio field recreated as x_field_1.

Bad:

```python
records.write({'x_studio_tier': 'gold'})
```

Good:

```python
records.write({'x_studio_tier_1': 'gold'})
```

Linted with `model=res.partner`; `sevlint remote` against a database whose fields are `res.partner`: name, x_studio_tier_1.

## E205

**Model that is not installed in the live database** (`missing-model-live`, error: fails when the line runs)

sevlint remote: env['model'] for a model not installed in the live database (KeyError). Not reported when guarded by `'model' in env` or inside try:.

Bad:

```python
vehicles = env['x_fleet.vehicle'].search([])
```

Good:

```python
if 'x_fleet.vehicle' in env:
    vehicles = env['x_fleet.vehicle'].search([])
```

Linted with `model=res.partner`; `sevlint remote` against a database whose fields are `res.partner`: name.

## W100

**XML: code after a comment is dropped** (`xml-dropped-text`, warning: data is lost or written differently than intended)

XML: text after a comment or child element inside <field name="code"> is dropped by Odoo (it stores node.text only).

Bad:

```xml
<odoo>
    <record id="action_demo" model="ir.actions.server">
        <field name="name">Demo</field>
        <field name="model_id" ref="sale.model_sale_order"/>
        <field name="state">code</field>
        <field name="code">
records.action_confirm()
<!-- then notify the salesperson -->
records.message_post(body='Confirmed')
</field>
    </record>
</odoo>
```

Good:

```xml
<odoo>
    <record id="action_demo" model="ir.actions.server">
        <field name="name">Demo</field>
        <field name="model_id" ref="sale.model_sale_order"/>
        <field name="state">code</field>
        <field name="code">
records.action_confirm()
# then notify the salesperson
records.message_post(body='Confirmed')
</field>
    </record>
</odoo>
```

## W110

**Accepted or rejected depending on the server's Python** (`python-dependent`, warning: rejected when the action is saved)

The verdict depends on the Python the Odoo server runs: comprehension closures and `(*a, b)` are rejected before 3.12, `@` on 3.10, `assert` before 3.14, newer syntax where it does not exist. Silenced when target-python pins the server's Python (then the verdict is exact).

Bad:

```python
def labels(partners, prefix):
    return [prefix + p.name for p in partners]

log(', '.join(labels(records, 'VIP ')))
```

Good:

```python
def labels(partners, prefix):
    out = []
    for p in partners:
        out.append(prefix + p.name)
    return out

log(', '.join(labels(records, 'VIP ')))
```

Linted with `odoo=19.0`.

## W203

**Field that the target version's Community does not have** (`removed-field`, warning: fails when the line runs)

Field not in the target version's Odoo Community (it is in another version) and no obvious rename: removed, or moved to an Enterprise/custom module.

Bad:

```python
lead = env['crm.lead'].browse(record.id)
number = lead.mobile
```

Good:

```python
lead = env['crm.lead'].browse(record.id)
number = lead.phone
```

Linted with `odoo=19.0`.

## W204

**write()/create() key that is not a field of the live database** (`unknown-vals-key-live`, warning: fails when the line runs)

sevlint remote: write()/create() key that is not a field of the live database's model: ValueError (Invalid field) unless the model's create()/write() override consumes the key.

Bad:

```python
records.write({'is_vip': True})
```

Good:

```python
records.write({'x_studio_is_vip': True})
```

Linted with `model=res.partner`; `sevlint remote` against a database whose fields are `res.partner`: name, x_studio_is_vip.

## W205

**Model that the target version's Community does not have** (`removed-model`, warning: fails when the line runs)

Model not in the target version's Odoo Community (it is in another version).

Bad:

```python
layers = env['stock.valuation.layer'].search([('product_id', '=', record.id)])
```

Good:

```python
moves = env['stock.move'].search([('product_id', '=', record.id), ('state', '=', 'done')])
```

Linted with `odoo=19.0`.

## W210

**Name that only an addon provides** (`addon-name`, warning: fails when the line runs)

Name provided only by an addon (json: base_automation/website, request: website, payload: base_automation + an HTTP request, never in scheduled runs). Declare installed modules with --modules or config. `request` in a scheduled action is an unbound proxy.

Bad:

```python
record.message_post(body=json.dumps({'id': record.id}))
```

Good:

```python
record.message_post(body=json.dumps({'id': record.id}))
```

Linted with the good example with `modules=base_automation`.

## W220

**Logged by the runtime sandbox, refused under unsafe-policy raise** (`sandbox-logged`, warning: rejected after a server configuration change)

Odoo 19.3+/20.0 with the default --unsafe-policy=log: bare `except:` / async code is logged by the sandbox and rejected once the server runs with --unsafe-policy=raise. Use `except Exception:`.

Bad:

```python
try:
    records.action_confirm()
except:
    log('confirmation failed', level='warning')
```

Good:

```python
try:
    records.action_confirm()
except Exception:
    log('confirmation failed', level='warning')
```

Linted with `odoo=saas-19.3`.

## W301

**env.cr.commit() or rollback() in a server action** (`commit`, warning: data is lost or written differently than intended)

env.cr.commit()/rollback() inside a server action: breaks atomicity of the action. Commits inside a loop of a scheduled action (batching) are not reported.

Bad:

```python
records.write({'comment': 'exported'})
env.cr.commit()
```

Good:

```python
records.write({'comment': 'exported'})
```

## W302

**Query per record (N+1)** (`query-in-loop`, warning: one query per record)

ORM query method (search, search_count, read_group, ...) inside a loop, a per-record lambda (filtered/mapped/sorted) or a helper called from one: one query per iteration. `search(..., limit=N)` in a while loop (batching) is not reported.

Bad:

```python
for order in records:
    n = env['sale.order.line'].search_count([('order_id', '=', order.id)])
    order.message_post(body=str(n))
```

Good:

```python
lines = env['sale.order.line'].search([('order_id', 'in', records.ids)])
for order in records:
    n = len(lines.filtered(lambda line: line.order_id == order))
    order.message_post(body=str(n))
```

Linted with `model=sale.order`.

## W303

**UserError after a write rolls the write back** (`rolled-back-write`, warning: data is lost or written differently than intended)

raise UserError after write/create/unlink on the same path: the exception rolls the transaction back. Fine for an intentional dry run (disable with `# sevlint: disable=W303`).

Bad:

```python
records.write({'note': 'checked'})
if any(order.amount_total > 10000 for order in records):
    raise UserError('Orders above 10 000 need approval')
```

Good:

```python
if any(order.amount_total > 10000 for order in records):
    raise UserError('Orders above 10 000 need approval')
records.write({'note': 'checked'})
```

Linted with `model=sale.order`.

## W304

**record/records in a scheduled action** (`record-in-cron`, warning: fails when the line runs)

record/records in a scheduled action (ir.cron): both are None there.

Bad:

```python
for order in records:
    order.action_confirm()
```

Good:

```python
for order in model.search([('state', '=', 'draft')]):
    order.action_confirm()
```

Linted with `caller=cron`, `model=sale.order`.

## W305

**record in an action offered for a selection** (`first-record-only`, warning: does something other than intended)

`record` without `records` in an action offered in list views (or kanban views on 19.0+): the code runs once, `record` is the first selected record, the rest is ignored.

Bad:

```python
record.action_confirm()
```

Good:

```python
records.action_confirm()
```

Linted with `binding=list,form`, `model=sale.order`.

## W306

**raise Exception shows a traceback** (`raise-exception`, warning: the user sees a traceback instead of a message)

raise Exception(...): safe_eval re-raises it as ValueError, the user sees a server error with traceback. Raise UserError for a message.

Bad:

```python
if not record.partner_id:
    raise Exception('Set a customer first')
```

Good:

```python
if not record.partner_id:
    raise UserError('Set a customer first')
```

Linted with `model=sale.order`.
