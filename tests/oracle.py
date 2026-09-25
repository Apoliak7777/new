"""Load Odoo's real safe_eval.py (vendored by tools/sync_odoo.py) with stubbed imports.

Odoo's ``test_python_expr`` is the ground truth for save-time checks: sevlint's
E0xx/E1xx must agree with it on every snippet, on every Python version CI runs.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "odoo"


def _stub(name: str, **attrs) -> types.ModuleType:
    module = sys.modules.get(name) or types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


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
    _stub("odoo.tools.misc", ustr=str)
    monkey = _stub("odoo._monkeypatches")
    monkey.__path__ = []
    _stub("odoo._monkeypatches.pytz", patch_pytz=lambda: None, patch_module=lambda: None)


def load(version: str) -> types.ModuleType:
    name = f"odoo.tools.safe_eval_{version.replace('.', '_')}"
    if name in sys.modules:
        return sys.modules[name]
    _install_stubs()
    spec = importlib.util.spec_from_file_location(name, FIXTURES / version / "safe_eval.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "odoo.tools"
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def rejects_on_save(version: str, code: str) -> bool:
    """What ir.actions.server._check_python_code does: test_python_expr(code.strip(), 'exec')."""
    module = load(version)
    try:
        return bool(module.test_python_expr(expr=code.strip(), mode="exec"))
    except NameError:  # assert_no_dunder_name raises NameError, which test_python_expr does not catch
        return True


def runtime_builtins(version: str) -> set[str]:
    return set(load(version)._BUILTINS)
