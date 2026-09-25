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

* **Offline by default, no dependencies**: stdlib only. No Odoo installation, database or API key.
  Optionally, `sevlint remote` reads the code actions of a live database (read-only) and checks them
  against that database's own version, modules and fields.
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

`sevlint versions` lists the supported Odoo series, `sevlint explain E101` describes a rule with
examples. Output formats: `text` (default), `json`, `github` (workflow annotations), `sarif` (code scanning).
Exit code: 0 clean, 1 errors (or warnings with `--strict`, or unreadable input), 2 usage/config error
(or, for `sevlint remote`, a connection/authentication error).

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

## Live database: `sevlint remote`

Server actions, scheduled actions and automation rules are often written in the Odoo UI and never
reach a repository. `sevlint remote` reads them from a running database and lints each one with
the database's own Odoo version, installed modules and fields (Enterprise, custom and Studio `x_`
fields included):

```bash
read -rs ODOO_API_KEY && export ODOO_API_KEY    # paste the key; it stays out of the shell history
sevlint remote https://mycompany.odoo.com                                   # Odoo 19+ / Odoo Online: JSON-2
sevlint remote https://erp.example.com --db prod --user admin@example.com   # 17.0/18.x: XML-RPC
sevlint remote https://mycompany.odoo.com --odoo 19.0     # upgrade check: lint against another version
sevlint remote https://mycompany.odoo.com --dump actions/ # also save each action as a .py with a header
```

```
ir.actions.server/412:2: E204 field `x_studio_tier` does not exist on `res.partner` in this database; similar: `x_studio_tier_1` (ValueError, fails at runtime) [19.0 server_action 'Set tier' __export__.ir_act_server_412_5f1c]
sevlint: mycompany.odoo.com: Odoo 19.0+e (Enterprise), 57 code action(s) read via JSON-2
```

* **What is read**: the version (`/web/webclient/version_info`, no login), then `search_read` on
  `ir.module.module`, `ir.actions.server` (state `code`), `ir.cron`, `base.automation`, `ir.model`
  and `ir.model.fields` (only the models the code uses). About 7 requests; on `*.odoo.com` sevlint
  keeps to one request per second and honours `Retry-After`.
* **Read-only**: the client calls no other method and refuses to (tested). Odoo API keys have
  no read-only scope, so this guarantee is sevlint's, not Odoo's: create a dedicated key and revoke
  it afterwards (Odoo 18+ lets you set a short duration). Reading server actions needs the
  *Administration / Settings* group. The only trace in the database: an XML-RPC login (17/18)
  is recorded in `res.users.log` like any login; JSON-2 requests are not.
* **The API key** comes from `$ODOO_API_KEY` (`--api-key-env` names another variable), the keyring
  (`keyring set sevlint mycompany.odoo.com`, if the `keyring` package is installed) or a hidden
  prompt; never from the command line. It is sent only to the given host: redirects are refused,
  plain `http://` only to localhost (`--allow-http` overrides) and never through a proxy, and it
  never appears in the output, even when the server echoes it. Server answers are untrusted:
  malformed ones end with a message and exit code 2, not a traceback.
* **Field checks against the database** replace the bundled index: **E204** a field the database
  does not have (in domains, `rec['x']`, `mapped()`/`filtered()`/`sorted()`/`read()`, and `rec.x` when
  `x` is an `x_` name or a field of some Odoo version), **W204** an unknown key in
  `write()`/`create()` values (an override may consume it), **E205** a model that is not installed
  (unless guarded by `'model' in env` or `try:`). With `--odoo` (another version) or `--no-schema`
  the bundled index is used instead.
* `--ids 12,40` and `--only cron,automation` narrow the run; `--format json|github` work as for
  `check`. `--dump` writes files for `sevlint check`; they may contain whatever the actions contain
  (hard-coded tokens included), so treat that directory like the database.

## Rules

Every rule with a failing and a fixed example: [docs/rules.md](docs/rules.md) (or `sevlint explain W302`).

| Code | When it hurts | What |
| --- | --- | --- |
| E001 | save | Syntax error, or code too long/deep for the compiler. `strip()` removes only the first line's indentation, so an indented block is an `IndentationError`. |
| E003 | install | XML: a child element inside `<field name="code">`; Odoo's `import_xml.rng` allows only text, so the module does not install. |
| E004 | save | saas-19.3+/20.0 with `--unsafe-policy=raise`/`terminate`: the runtime sandbox refuses bare `except:`, `async def` and async comprehensions. |
| E101 | save | Forbidden opcode: `import`, `obj.attr = x`, `del d[k]`, `assert` (before Python 3.14), `with`, `class`, closures (an inner function/lambda using the outer function's variables), `a, *b = x`, `global`, `:=` in a top-level comprehension, `yield from`, `match` with sequence/mapping/class patterns, annotated assignments. |
| E102 | save | Forbidden name: any name or attribute containing `__` (also `my__var`), `mro`, `f_globals`, …, and a docstring as the first statement (`__doc__`). String literals are fine. |
| E201 | runtime | Name not in the context or builtins: `type`, `getattr`, `hasattr`, `print`, `dir`, `ValueError`, `KeyError`, … |
| E203 | runtime | Field renamed between versions, e.g. `res.users.groups_id` → `group_ids` (saas-18.2+), `sale.order.line.tax_id` → `tax_ids`. |
| W203 | runtime | Field that another Odoo version has but the target's Community does not (removed, or moved to Enterprise). |
| W205 | runtime | Model that another Odoo version has but the target's Community does not. |
| E204 | runtime | `sevlint remote`: field that the live database does not have (Studio `x_` fields included), e.g. a Studio field recreated as `x_field_1`. |
| W204 | runtime | `sevlint remote`: key in `write()`/`create()` values that is not a field of the live database's model (unless the model's override consumes it). |
| E205 | runtime | `sevlint remote`: `env['model']` for a model that is not installed in the live database. |
| E202 | runtime | Attribute not exposed by wrapped `datetime`, `dateutil`, `time` (e.g. `time.mktime`, `dateutil.easter`). |
| W110 | save | Rejected by Odoo on another Python the target version supports (comprehension closures before 3.12, `(*a, b)` before 3.12, `@` on 3.10, `assert` before 3.14, newer syntax). |
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

## Fields across versions

A field index of every Odoo Community model in all 16 supported versions ships with sevlint
(`tools/fields_index.py` builds it from the Odoo sources, 130 KiB). Where the model of an
expression is obvious (`env['res.users']`, `user`, `env.company`, `record`/`records` of an action
whose `model_id` is known, names assigned from those, loop variables), field names in attribute
access, `write`/`create` values, domains, `mapped`/`filtered`/`read` strings are checked against
the target version. Only names Odoo had in *some* version are judged, so Enterprise, Studio (`x_`)
and custom fields are never reported. Set the model of a `.py` snippet with the header key
`model=res.partner`.

## Python version matters

Odoo checks **bytecode** produced by the Python it runs on (17.0–19.0 accept 3.10–3.14), and
sevlint compiles with the Python it runs on. These constructs flip between versions:

| Construct | 3.10 | 3.11 | 3.12–3.13 | 3.14 |
| --- | --- | --- | --- | --- |
| list/dict/set comprehension inside `def` using the function's locals | rejected | rejected | allowed (PEP 709) | allowed |
| tuple display with `*` unpacking `(*a, b)` | rejected | rejected | allowed | allowed |
| `a @ b` | rejected | allowed | allowed | allowed |
| `assert` | rejected | rejected | rejected | allowed |

sevlint knows these differences: when the code passes on the Python it runs on but Odoo would
reject it on another Python the target version supports, it reports **W110** with the exact
versions (verified against Odoo's real `safe_eval` under all five Pythons in CI). For an exact
verdict, run sevlint on the server's Python, e.g.
`uvx --python 3.10 --from git+https://github.com/Apoliak7777/new sevlint check .`, and set
`target-python` so a mismatch fails loudly; W110 is then silenced.

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

`--format github` annotates the pull request. For the *Security → Code scanning* tab, write SARIF
and upload it (public repositories, or private ones with GitHub Advanced Security):

```yaml
permissions:
  contents: read
  security-events: write
steps:
  - uses: actions/checkout@v7
  - uses: actions/setup-python@v7
    with: {python-version: "3.12"}
  - run: pip install git+https://github.com/Apoliak7777/new
  - run: sevlint check . --format sarif > sevlint.sarif || true   # findings must not stop the upload
  - uses: github/codeql-action/upload-sarif@v4
    with: {sarif_file: sevlint.sarif, category: sevlint}
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
* Current results: 0 findings on the server actions and crons shipped with Odoo Community in all 16
  versions (157-300 snippets each from data, views, wizard and report XML; the one exception is a
  genuine W305 in saas-19.4/20.0 `payment`) and on 40 snippets from eight OCA 17.0 repositories.
* The field checks were run over Odoo's own model code (`self` typed as the class's model): of
  6 000-7 300 field names per version in domains, vals, `mapped()`/`sorted()`/`read()` strings,
  none was missing from the index except names that only abstract mixins use.

## Limitations

* Offline field checks know Odoo Community only (Enterprise, Studio and custom fields are never
  reported); `sevlint remote` checks against the real database. Either way only expressions whose
  model is obvious are checked.
* Enterprise or custom modules may add context names; declare them with `names`.
* Which Python Odoo Online (SaaS) runs is not published; pick the closest `target-python`.
* The W rules are heuristics.

## Also in this repository

[`dotacie/`](dotacie/): a comparison of Czech grant calls for grant consulting (in Slovak) and Czech blog posts about
the current calls for an Odoo website, unrelated to the linter.

## License

LGPL-3.0 (like Odoo; `tests/fixtures/odoo/*/safe_eval.py` are copied from Odoo S.A.'s repository).
