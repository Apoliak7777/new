# Changelog

All notable changes to sevlint. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/). Rule codes are stable: a code
keeps its meaning across releases, new checks get new codes.

## [0.2.0]

### Added
- **Odoo Online and 20.0**: profiles for saas-17.1 … saas-19.4 and 20.0 (16 versions in total), each
  with its supported Python range. `--odoo 19.2`, `saas~19.2` and `saas-19.2` are accepted.
- **Runtime sandbox of saas-19.3+/20.0**: E004 (refused under `--unsafe-policy=raise/terminate`) and
  W220 (logged under the default `log`) for bare `except:` and async code; `--unsafe-policy` option
  and `unsafe-policy` config key.
- **Fields across versions**: a bundled index of every Community model's fields in all 16 versions;
  E203 renamed field (`res.users.groups_id` → `group_ids`, `sale.order.line.tax_id` → `tax_ids`),
  W203 removed field, W205 removed model. The `model=` header key and `model_id` in XML give
  `record`/`records` their model.
- **W110**: code whose save-time verdict depends on the Python the Odoo server runs (comprehension
  closures and `(*a, b)` before 3.12, `@` on 3.10, `assert` before 3.14, newer syntax), verified against
  Odoo's real `safe_eval` under Python 3.10–3.14 in CI.
- **`sevlint remote`**: lints the server actions, scheduled actions and automation rules of a live
  database, read-only (JSON-2 on 19+, XML-RPC on 17/18), with that database's version, modules and
  fields: E204 missing field (Studio `x_` fields included), W204 unknown `write()`/`create()` key,
  E205 model not installed. `--odoo` for an upgrade check, `--dump` to save the code for `sevlint check`.
- **SARIF 2.1.0 output** (`--format sarif`) for GitHub code scanning and SARIF viewers.
- **Rule catalog**: every rule has a name, a failing and a fixed example (all linted by the test suite);
  `sevlint explain CODE` shows them and [docs/rules.md](docs/rules.md) lists them.
- Release workflow: tag `vX.Y.Z` builds, checks and attaches the wheel and sdist to a GitHub release
  (PyPI publishing is opt-in).

### Changed
- `sevlint explain` without a code lists the rules as `CODE name title`.
- The weekly upstream check covers all 16 Odoo branches.
- Text output sorts paths naturally (`ir.actions.server/9` before `/10`).

## [0.1.0]

### Added
- First release: save-time checks identical to Odoo's `_check_python_code` for 17.0, 18.0 and 19.0
  (E001, E101, E102), runtime checks (E201, E202, W210, W301–W306), XML checks (E003, W100),
  `.py` snippets with a `# sevlint:` header, stdin, config in `pyproject.toml`/`.sevlint.toml`,
  pre-commit hook, GitHub Actions annotations (`--format github`) and a Claude Code plugin.

[0.2.0]: https://github.com/Apoliak7777/new/compare/0a135f6...v0.2.0
[0.1.0]: https://github.com/Apoliak7777/new/commit/0a135f6
