# sevlint

A linter for Odoo **server action code**: `ir.actions.server` (state `code`), scheduled actions
(`ir.cron`) and the actions behind automation rules. It catches what Odoo's `safe_eval` rejects
when you save, and what crashes later at runtime, before the code reaches a database.

```
$ sevlint check examples
examples/sevlint_demo/data/server_actions.xml:10: E201 name `hasattr` is not defined in the server action context (NameError, fails at runtime) [19.0 server_action action_mark_vip]
examples/sevlint_demo/data/server_actions.xml:12: E101 attribute assignment `obj.attr = value` is not allowed (opcode STORE_ATTR); use record.write({'attr': value}) (rejected when saving in Odoo) [19.0 server_action action_mark_vip]
examples/sevlint_demo/data/server_actions.xml:21: W304 `records` is None when the action runs from a scheduled action (no active_model); use model.search(...) [19.0 cron cron_followup]
examples/snippet.py:2: E102 a bare string as the first statement is a docstring and stores '__doc__'; use # comments (rejected when saving in Odoo) [17.0 server_action]
examples/snippet.py:7: E202 `time.mktime` is not exposed by Odoo's wrapped `time` (allowed: sleep, strftime, strptime, time; AttributeError, fails at runtime) [17.0 server_action]
...
```

* **Offline, no dependencies**: stdlib only. No Odoo installation, database or API key needed.
* **Same verdict as Odoo**: the save-time check re-implements `_check_python_code` →
  `test_python_expr(code.strip(), "exec")` with data extracted from Odoo's own `safe_eval.py`
  for 17.0, 18.0 and 19.0. The test suite compares every verdict with the real `safe_eval.py`.
* **Beyond Odoo's own check**: undefined names, attributes that wrapped modules do not expose,
  and a handful of common bugs (N+1 queries, `cr.commit()`, rollback by `UserError`, `records` in crons).

## Install / run

```bash
# one-off, no install (uv)
uvx --from git+https://github.com/Apoliak7777/new sevlint check path/to/addons

# or install
pip install git+https://github.com/Apoliak7777/new
sevlint check my_module/
```

Paste code from the Odoo UI straight in:

```bash
pbpaste | sevlint check - --odoo 18.0 --caller cron
```

`sevlint versions` lists the supported Odoo series, `sevlint explain E101` describes a rule.

## What gets linted

| Input | How |
| --- | --- |
| `*.xml` module data | `<record>` of `ir.actions.server`, `ir.cron`, `base.automation` with a `code` field (skipped if `state` is not `code`). The caller comes from the model; `base_automation_id` means automation. |
| `*.py` with a header | Any file whose first 10 lines contain `# sevlint: ...`. Other `.py` files are ignored unless you pass `--all-py`. |
| stdin | `sevlint check -` (the header is optional) |

The Odoo series comes from the header, then the nearest `__manifest__.py` (`19.0.x.y.z`), then
`--odoo`/config, then defaults to `19.0`. Installed modules are taken from the manifest's
`depends`, followed through sibling modules in the same addons directory.

Header keys (all optional):

```python
# sevlint: odoo=18.0 caller=cron modules=website,base_automation names=my_helper disable=W302 binding=list,form
```

## Rules

| Code | When it hurts | What |
| --- | --- | --- |
| E001 | save | Syntax error. Odoo strips the code, so an indented first line is an `IndentationError`. |
| E101 | save | Forbidden opcode: `import`, `obj.attr = x`, `del d[k]`, `assert`, `with`, `class`, closures, `a, *b = x`, `global`, `:=` in a top-level comprehension, `yield from`, `match` with sequence/mapping/class patterns, annotations. |
| E102 | save | Forbidden name: any name or attribute containing `__` (also `my__var`), `mro`, `f_globals`, …, and a docstring as the first statement (`__doc__`). String literals are fine. |
| E201 | runtime | Name not in the context or builtins: `type`, `getattr`, `hasattr`, `print`, `dir`, `ValueError`, `KeyError`, … |
| E202 | runtime | Attribute not exposed by wrapped `datetime`, `dateutil`, `time` (e.g. `time.mktime`, `dateutil.easter`). |
| W210 | runtime | `json`/`payload` need `base_automation` (`json` also comes with `website`), `request` needs `website`. |
| W301 | data | `env.cr.commit()` / `rollback()` inside the action. |
| W302 | performance | `search`/`search_count`/`read_group`/… inside a loop. |
| W303 | data | `raise UserError` after `write`/`create`/`unlink`/…: everything is rolled back. |
| W304 | runtime | `record`/`records` in a scheduled action: both are `None` there. |
| W305 | logic | `record` without `records` in an action offered in list views: only the first selected record is processed. |
| W306 | UX | `raise Exception(...)`: the user gets a server error; raise `UserError`. |

Suppress on one line with `# sevlint: disable=W302` (or bare `# sevlint: disable`), for a whole
run with `--disable W302,W303`, or all warnings with `--disable W*`.

## Python version matters

Odoo checks **bytecode** produced by the Python it runs on (17.0–19.0 accept 3.10–3.14), and
sevlint compiles with the Python it runs on. These constructs flip between versions:

| Construct | 3.10 | 3.11 | 3.12–3.13 | 3.14 |
| --- | --- | --- | --- | --- |
| list/dict/set comprehension inside `def` using the function's locals | rejected | rejected | allowed (PEP 709) | allowed |
| tuple display with `*` unpacking `(*a, b)` | rejected | rejected | allowed | allowed |
| `a @ b` | rejected | allowed | allowed | allowed |
| `assert` | rejected | rejected | rejected | allowed |

Run sevlint on the server's Python, e.g. `uvx --python 3.10 --from git+https://github.com/Apoliak7777/new sevlint check .`,
and set `target-python` so a mismatch fails loudly instead of giving a wrong verdict.

## Configuration

`pyproject.toml` (or a top-level `.sevlint.toml`):

```toml
[tool.sevlint]
odoo = "18.0"                       # when no header / manifest says otherwise
modules = ["website", "base_automation"]
names = ["my_enterprise_helper"]    # extra context names (Enterprise / custom _get_eval_context)
disable = ["W302"]
target-python = "3.12"              # fail if not running on this Python
```

## Integrations

### pre-commit

```yaml
repos:
  - repo: https://github.com/Apoliak7777/new
    rev: main  # pin a tag or commit SHA
    hooks:
      - id: sevlint
```

### GitHub Actions

```yaml
- uses: actions/setup-python@v6
  with: {python-version: "3.12"}
- run: pipx run --spec git+https://github.com/Apoliak7777/new sevlint check . --format github
```

### Claude Code plugin

The repository is also a Claude Code plugin marketplace. After every `Write`/`Edit` of a `.py`/`.xml`
file the plugin's hook lints the file and returns the findings to Claude, and a skill tells Claude
the rules of server action code up front.

```
/plugin marketplace add Apoliak7777/new
/plugin install sevlint@sevlint
```

The hook runs `python3` from the plugin directory (no install, no network). It stays silent for
files without server action code.

## How it stays correct

* `tools/sync_odoo.py 17.0 18.0 19.0` sparse-clones `odoo/odoo`, extracts opcode lists,
  `_UNSAFE_ATTRIBUTES`, `_BUILTINS`, wrapped-module whitelists and every `_get_eval_context` of
  `ir.actions.server` **from the AST** (never imports Odoo), writes `src/sevlint/data/odoo-*.json` and
  vendors `safe_eval.py` into `tests/fixtures/`. Anything it does not recognise aborts the sync.
* `tests/test_oracle.py` loads the vendored `safe_eval.py` (imports stubbed) and asserts, on every
  Python version in CI, that the opcode set, builtins and wrapped modules are identical, and that
  sevlint rejects exactly the snippets Odoo rejects.
* A weekly workflow re-runs the sync against the Odoo branches and fails when upstream changes.
* Checked against every server action and cron shipped in Odoo Community 17.0/18.0/19.0
  (168/227/235 snippets): 0 findings.

## Limitations

* No database, so no field checks: `user.groups_id` is valid on 17/18 but renamed to `group_ids` in 19.0,
  and sevlint cannot tell.
* Enterprise or custom modules may add context names; declare them with `names`.
* Which Python Odoo Online (SaaS) runs is not published; pick the closest `target-python`.
* The W rules are heuristics.

## License

LGPL-3.0 (like Odoo; `tests/fixtures/odoo/*/safe_eval.py` are copied from Odoo S.A.'s repository).
