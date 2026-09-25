---
name: sevlint
description: Rules for writing Odoo server action code (ir.actions.server state=code, ir.cron, automation rule actions) that passes safe_eval, plus how to check it with sevlint. Use when writing, editing or reviewing Python that runs inside Odoo's safe_eval, whether it sits in module XML data, is pasted into the Odoo UI or kept in a .py file with a "# sevlint:" header.
---

# Odoo server action code (safe_eval), verified for 17.0 / 18.0 / 19.0

Odoo stores `code.strip()` and on save runs `test_python_expr(..., mode="exec")`: bytecode and
name checks only. Undefined names are only found when the line runs. After writing such code, run
`sevlint check <file>` (or `sevlint check - --odoo 19.0 --caller cron` with the code on stdin).
The plugin hook does this automatically after each Write/Edit.

## Available names
- Context: `env`, `model`, `record`, `records`, `uid`, `user`, `time`, `datetime`, `dateutil`,
  `timezone` (pytz.timezone), `float_compare`, `b64encode`, `b64decode`, `Command`, `UserError`,
  `log(message, level="info")`, `_logger` (info/warning/error/exception, no debug).
- `json` only with `base_automation` or `website`; `request` only with `website`; `payload` only for webhooks.
- Builtins (complete list): `True False None abs all any bool bytes chr dict divmod enumerate
  Exception filter float int isinstance len list map max min ord range reduce repr round set sorted
  str sum tuple zip unicode xrange`.
- NOT available: `type`, `getattr`, `hasattr`, `setattr`, `print`, `dir`, `iter`, `next`, `ValueError`,
  `KeyError`, `TypeError` and every other exception except `Exception` and `UserError`.
- Wrapped modules expose only: `datetime.{date,datetime,time,timedelta,timezone,tzinfo,MINYEAR,MAXYEAR}`,
  `dateutil.{parser,relativedelta,rrule,tz}`, `time.{time,strptime,strftime,sleep}`.

## Rejected when saving
- `import` / `from ... import`.
- Attribute assignment `record.x = v` / `record.x += 1` / `del record.x`: use `record.write({'x': v})`.
- `del d[k]` (use `d.pop(k)`), `assert`, `with`, `class`, `global`, `a, *b = x`, `yield from`,
  `match` with sequence/mapping/class patterns, annotated assignments at top level.
- Any name or attribute containing `__` anywhere (`__class__`, `my__var`) or named `mro`, `f_globals`,
  `gi_frame`, …. String literals with `__` are fine (`'__TEST__'` is OK).
- A string as the first statement (docstring → `__doc__`). Use `#` comments.
- Closures: an inner function or lambda using a variable of its enclosing function. On Python ≤ 3.11
  also list/dict/set comprehensions inside a `def` that use the function's locals; generator
  expressions inside a `def` using its locals are rejected on every version. Top-level code is fine:
  top-level names are globals.
- `:=` inside a comprehension at top level.
- An indented first line (the code is stripped, the rest keeps its indentation).

## Behaviour to design for
- A code action runs once. From a list view `records` = all selected, `record` = only the first one.
  In a cron both are `None`: use `model.search(...)`.
- Return a client action by assigning `action = {...}` (no top-level `return`).
- `raise UserError(...)` rolls back everything written in the transaction (only `log()` survives,
  it uses its own cursor). To persist writes and inform the user, set
  `action = {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {...}}`.
- `raise Exception(...)` reaches the user as a server error; raise `UserError` for messages.
- Never `env.cr.commit()`. Avoid `search`/`search_count` inside loops: query once with `in` and use
  `mapped`/`filtered`/`_read_group`.
- Field names differ between versions (e.g. `res.users.groups_id` in 17/18 → `group_ids` in 19); sevlint
  cannot check fields, so verify them against the target version.
