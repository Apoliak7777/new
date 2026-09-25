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

* **Offline, no dependencies**: stdlib only. No Odoo installation, database, server or API key.
* **Same verdict as Odoo**: the save-time check re-implements `_check_python_code` →
  `test_python_expr(code.strip(), "exec")` with data extracted from Odoo's own `safe_eval`
  for **17.0, 18.0, 19.0, 20.0 and every Odoo Online release saas-17.1 … saas-19.4**. The test suite
  compares every verdict with the real `safe_eval` of each version, including the 19.3+ runtime sandbox.
* **Beyond Odoo's own check**: undefined names, attributes that wrapped modules do not expose,
  and common bugs (N+1 queries, `cr.commit()`, rollback by `UserError`, `records` in crons).

## Try it

```bash
# no install, needs uv (https://docs.astral.sh/uv/)
uvx --from git+https://github.com/Apoliak7777/new sevlint check path/to/addons

# or install with pip (Python 3.10+)
pip install git+https://github.com/Apoliak7777/new
sevlint check path/to/addons
```

The repository contains a deliberately broken demo module: `sevlint check examples` reports 8 errors
and 5 warnings. Code copied from the Odoo UI can be piped in:

```bash
pbpaste | sevlint check - --odoo 18.0 --caller cron            # macOS
Get-Clipboard | sevlint check - --odoo 18.0 --caller cron      # Windows PowerShell
```

`sevlint versions` lists the supported Odoo series, `sevlint explain E101` describes a rule.
Exit code: 0 clean, 1 errors (or warnings with `--strict`, or unreadable input), 2 usage/config error.

## What gets linted

| Input | How |
| --- | --- |
| `*.xml` module data | Every `<record>` of `ir.actions.server`, `ir.cron`, `base.automation` with a `code` field, including records nested in `action_server_ids`. `eval="'...'"` and `file="module/path.py"` values are understood, as are the declared encoding (UTF-8, UTF-16, Shift_JIS, ...). The code is read the way Odoo stores it (text before the first comment; the last `code` field wins). If the action's `state` is not `code` (a server action without `state` never runs code: 17/18 default to `object_write`), only the save-time checks run: Odoo validates the code of every action anyway. |
| `*.py` with a header | Files whose leading comment block (first 10 lines) contains `# sevlint: ...`. Other `.py` files are ignored unless you pass `--all-py`. |
| stdin | `sevlint check -` (the header is optional) |

The Odoo series comes from the header, then the nearest `__manifest__.py` (`19.0.x.y.z`), then
`--odoo`/config, then defaults to `19.0`. Odoo Online versions are written `saas-19.2`; the forms
`saas~19.2` (what Odoo shows) and `19.2` are accepted too. `sevlint versions` lists them all. Installed modules are the module itself plus its
`depends`, followed through sibling modules of the same addons directory (symlinked modules too).

Header keys (all optional):

```python
# sevlint: odoo=18.0 caller=cron modules=website,base_automation names=my_helper disable=W302 binding=list,form
```

## Rules

| Code | When it hurts | What |
| --- | --- | --- |
| E001 | save | Syntax error, or code too long/deep for the compiler. `strip()` removes only the first line's indentation, so an indented block is an `IndentationError`. |
| E003 | install | XML: a child element inside `<field name="code">`; Odoo's `import_xml.rng` allows only text, so the module does not install. |
| E004 | save | saas-19.3+/20.0 with `--unsafe-policy=raise`/`terminate`: the runtime sandbox refuses bare `except:`, `async def` and async comprehensions. |
| E101 | save | Forbidden opcode: `import`, `obj.attr = x`, `del d[k]`, `assert` (before Python 3.14), `with`, `class`, closures (an inner function/lambda using the outer function's variables), `a, *b = x`, `global`, `:=` in a top-level comprehension, `yield from`, `match` with sequence/mapping/class patterns, annotated assignments. |
| E102 | save | Forbidden name: any name or attribute containing `__` (also `my__var`), `mro`, `f_globals`, …, and a docstring as the first statement (`__doc__`). String literals are fine. |
| E201 | runtime | Name not in the context or builtins: `type`, `getattr`, `hasattr`, `print`, `dir`, `ValueError`, `KeyError`, … |
| E202 | runtime | Attribute not exposed by wrapped `datetime`, `dateutil`, `time` (e.g. `time.mktime`, `dateutil.easter`). |
| W100 | data | XML: code after a comment or child element inside `<field name="code">` is dropped by Odoo. |
| W220 | future | saas-19.3+/20.0 with the default `--unsafe-policy=log`: the same constructs are only logged, but rejected once the server switches to `raise`. |
| W210 | runtime | `json` needs `base_automation` or `website`, `request` needs `website` (and is unbound in scheduled actions), `payload` needs `base_automation` and an HTTP request (never in scheduled runs). |
| W301 | data | `env.cr.commit()` / `rollback()` (also via `cr = env.cr`). Commits inside a batch loop of a scheduled action are fine. |
| W302 | performance | `search`/`search_count`/`read_group`/… per iteration: in loops, in lambdas given to `filtered`/`mapped`/`sorted`, or in a helper called from a loop. `search(..., limit=N)` batches in a `while` loop are fine. |
| W303 | data | `raise UserError` after `write`/`create`/`unlink`/… on the same path: everything is rolled back. |
| W304 | runtime | `record`/`records` in a scheduled action: both are `None` there. |
| W305 | logic | `record` without `records` in an action offered in list views (kanban too on 19.0): only the first selected record is processed. |
| W306 | UX | `raise Exception(...)` not caught locally: the user gets a server error; raise `UserError`. |

Suppress on one line with `# sevlint: disable=W302` (or bare `# sevlint: disable`), for a whole
file with the header `disable=`, for a run with `--disable W302,W303`, or all warnings with `--disable W*`.

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

`pyproject.toml` (or a `.sevlint.toml` with the same keys at top level). The nearest config above
each path given on the command line is used; `--config` forces one.

```toml
[tool.sevlint]
odoo = "18.0"                       # when no header / manifest says otherwise
modules = ["website", "base_automation"]
names = ["my_enterprise_helper"]    # extra context names (Enterprise / custom _get_eval_context)
disable = ["W302"]
target-python = "3.12"              # quoted; fail if not running on this Python
unsafe-policy = "raise"             # saas-19.3+/20.0 server option --unsafe-policy (default "log")
```

Reading config needs Python 3.11+ (or the `tomli` package on 3.10).

## Integrations

### pre-commit

```yaml
repos:
  - repo: https://github.com/Apoliak7777/new
    rev: <tag or commit SHA>   # pre-commit does not accept branch names
    hooks:
      - id: sevlint
```

### GitHub Actions

```yaml
- uses: actions/setup-python@v7
  with: {python-version: "3.12"}   # the Python your Odoo server runs
- run: pip install git+https://github.com/Apoliak7777/new
- run: sevlint check . --format github
```

### Claude Code plugin

The repository is also a Claude Code plugin marketplace. After every `Write`/`Edit` of a `.py`/`.xml`
file the plugin's hook lints that file and returns the findings to Claude (exit 2, so Claude sees them
and fixes the code), and a skill tells Claude the rules of server action code up front.

```
/plugin marketplace add Apoliak7777/new
/plugin install sevlint@sevlint
```

To try a local checkout without installing: `claude --plugin-dir path/to/this/repo`.

The hook runs from the plugin directory with no install and no network. `hooks/run.sh` uses
`$SEVLINT_PYTHON` if set, else the first working Python 3.10+ among `python3`, `python`, `py` (so the
Windows Store `python3` alias is skipped). On Windows it needs Git Bash, which Claude Code uses for
hook commands. Set `SEVLINT_PYTHON` to the same Python version as your Odoo server.

The hook stays silent for files without server action code, for Odoo 16.0 and older modules and for
XML that is not Odoo data. Findings go to Claude with the rule explanations inline; a mismatch with
`target-python` on an otherwise clean file is shown to you instead. On Python 3.10 without `tomli`
the project config is ignored (with a note).

## How it stays correct

* `tools/sync_odoo.py 17.0 18.0 19.0` sparse-clones `odoo/odoo`, extracts opcode lists,
  `_UNSAFE_ATTRIBUTES`, `_BUILTINS`, wrapped-module whitelists and every `_get_eval_context` of
  `ir.actions.server` **from the AST** (never imports Odoo), writes `src/sevlint/data/odoo-*.json` and
  vendors `safe_eval.py` into `tests/fixtures/`. Anything it does not recognise aborts the sync.
* `tests/test_oracle.py` loads the vendored `safe_eval.py` (imports stubbed) and asserts, on every
  Python version in CI (3.10–3.14), that the opcode set, builtins and wrapped modules are identical,
  and that sevlint rejects exactly the snippets Odoo rejects.
* A weekly workflow checks the data against the Odoo branches (`--check`) and lints every server
  action shipped with Odoo Community as a false-positive regression test.
* Current results: 0 findings on the server actions and crons in Odoo Community 17.0/18.0/19.0
  (174/233/242 snippets from data, views, wizard and report XML) and on 40 snippets from eight OCA
  17.0 repositories.

## Limitations

* No database, so no field checks: `user.groups_id` is valid on 17/18 but renamed to `group_ids` in 19.0,
  and sevlint cannot tell.
* Enterprise or custom modules may add context names; declare them with `names`.
* Which Python Odoo Online (SaaS) runs is not published; pick the closest `target-python`.
* The W rules are heuristics.

## License

LGPL-3.0 (like Odoo; `tests/fixtures/odoo/*/safe_eval.py` are copied from Odoo S.A.'s repository).
