"""Load Odoo's real safe_eval (vendored by tools/sync_odoo.py) with stubbed imports.

Odoo's ``test_python_expr`` is the ground truth for save-time checks: sevlint's
E0xx/E1xx must agree with it on every snippet, on every Python version CI runs.

Two layouts are vendored: ``safe_eval.py`` (up to saas-19.2) and the ``safe_eval/``
package with the runtime sandbox (saas-19.3+, 20.0), which rewrites the code with
``safe_transform`` before the opcode check when ``--unsafe-policy`` is not ``disable``.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "odoo"
SANDBOX_TOOL_ID = 4  # sys.monitoring tool id claimed by odoo/tools/safe_eval/runtime.py


def _stub(name: str, **attrs) -> types.ModuleType:
    module = sys.modules.get(name) or types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class _OrderedSet(dict):
    def __init__(self, items=()):
        super().__init__((item, None) for item in items)


class _Lazy:
    def __init__(self, func):
        self._func = func


def _install_stubs() -> None:
    exc = type("StubError", (Exception,), {})
    _stub("psycopg2", OperationalError=type("OperationalError", (Exception,), {}),
          IntegrityError=type("IntegrityError", (Exception,), {}))
    werkzeug = _stub("werkzeug")
    werkzeug.exceptions = _stub("werkzeug.exceptions", HTTPException=type("HTTPException", (Exception,), {}))
    odoo = _stub("odoo")
    odoo.__path__ = []  # make it a package for relative imports
    odoo.exceptions = _stub("odoo.exceptions", UserError=type("UserError", (Exception,), {}),
                            RedirectWarning=type("RedirectWarning", (Exception,), {}),
                            ConcurrencyError=type("ConcurrencyError", (Exception,), {}), StubError=exc)
    tools = _stub("odoo.tools")
    tools.__path__ = []
    odoo.tools = tools
    _stub("odoo.tools.misc", ustr=str, OrderedSet=_OrderedSet)
    _stub("odoo.tools.func", lazy=_Lazy)
    _stub("odoo.tools.config", config={"unsafe_policy": "log", "upgrade_path": []})
    monkey = _stub("odoo._monkeypatches")
    monkey.__path__ = []
    _stub("odoo._monkeypatches.pytz", patch_pytz=lambda: None, patch_module=lambda: None)


def has_sandbox(version: str) -> bool:
    return (FIXTURES / version / "safe_eval").is_dir()


def load(version: str, policy: str = "log") -> types.ModuleType:
    key = version.replace(".", "_").replace("-", "_")
    _install_stubs()
    single = FIXTURES / version / "safe_eval.py"
    if single.exists():
        name = f"odoo.tools.se_{key}"
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, single)
            module = importlib.util.module_from_spec(spec)
            module.__package__ = "odoo.tools"
            sys.modules[name] = module
            spec.loader.exec_module(module)
        return sys.modules[name]

    name = f"odoo.tools.se_{key}_{policy}"
    if name not in sys.modules:
        if sys.version_info < (3, 12):
            raise RuntimeError(f"Odoo {version}'s safe_eval needs Python 3.12+ (sys.monitoring)")
        # runtime.py binds `config` and claims a sys.monitoring tool id at import time.
        sys.modules["odoo.tools.config"].config = {"unsafe_policy": policy, "upgrade_path": []}
        if sys.monitoring.get_tool(SANDBOX_TOOL_ID) is not None:
            sys.monitoring.free_tool_id(SANDBOX_TOOL_ID)
        package_dir = FIXTURES / version / "safe_eval"
        spec = importlib.util.spec_from_file_location(name, package_dir / "__init__.py",
                                                      submodule_search_locations=[str(package_dir)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def rejects_on_save(version: str, code: str, policy: str = "log") -> bool:
    """What ir.actions.server._check_python_code does: test_python_expr(code.strip(), 'exec')."""
    module = load(version, policy)
    try:
        return bool(module.test_python_expr(expr=code.strip(), mode="exec"))
    except NameError:  # assert_no_dunder_name raises NameError, which test_python_expr does not catch
        return True


def runtime_builtins(version: str) -> set[str]:
    return set(load(version)._BUILTINS)
