"""A tiny stand-in for an Odoo server: /web/webclient/version_info, JSON-2 and XML-RPC.

It serves search_read over in-memory tables with Odoo's semantics that sevlint relies on
(domains with = / in, active_test, offset/limit/order id, unknown fields rejected) and
records every request so tests can assert what was sent.
"""
from __future__ import annotations

import json
import threading
import xmlrpc.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = "0123456789abcdef0123456789abcdef01234567"
LOGIN = "admin"
DB = "testdb"
UID = 2


class OdooError(Exception):
    def __init__(self, status: int, name: str, message: str):
        super().__init__(message)
        self.status, self.name, self.message = status, name, message


class MockOdoo:
    def __init__(self, series: str = "19.0", enterprise: bool = False, tables: dict | None = None):
        self.series = series
        self.enterprise = enterprise
        self.tables: dict[str, list[dict]] = tables or {}
        self.requests: list[dict] = []
        self.fail_once: dict[str, tuple[int, dict]] = {}  # path -> (status, headers)
        self.redirect: dict[str, str] = {}  # path -> Location
        self.html_everywhere = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    @property
    def json2_available(self) -> bool:
        major = self.series.removeprefix("saas~").split(".")[0]
        return int(major) >= 19

    def version_info(self) -> dict:
        saas = self.series.startswith("saas~")
        major, minor = self.series.removeprefix("saas~").split(".")
        info = [f"saas~{major}" if saas else int(major), int(minor), 0, "final", 0, "e" if self.enterprise else ""]
        return {"server_version": self.series + ("+e" if self.enterprise else ""), "server_version_info": info,
                "server_serie": self.series, "protocol_version": 1}

    # -- ORM ------------------------------------------------------------------------------
    def search_read(self, model: str, domain=None, fields=None, offset=0, limit=None, order=None, context=None):
        if model not in self.tables:
            raise OdooError(404, "werkzeug.exceptions.NotFound", f"the model {model!r} does not exist")
        rows = self.tables[model]
        known = set().union(*(r.keys() for r in rows)) if rows else set(fields or [])  # empty: any field
        for name in fields or []:
            if name not in known:
                raise OdooError(500, "builtins.ValueError", f"Invalid field {name!r} on model {model!r}")
        domain = [list(leaf) for leaf in domain or []]
        if (context or {}).get("active_test", True) and "active" in known and not any(l[0] == "active" for l in domain):
            domain.append(["active", "=", True])
        out = []
        for row in sorted(rows, key=lambda r: r["id"]):
            if all(self._match(row, leaf) for leaf in domain):
                out.append({"id": row["id"], **{f: row.get(f, False) for f in fields or known}})
        out = out[offset or 0:]
        return out[:limit] if limit else out

    @staticmethod
    def _match(row: dict, leaf: list) -> bool:
        name, op, value = leaf
        actual = row.get(name, False)
        if isinstance(actual, list) and actual and op == "=":  # many2one [id, name]
            actual = actual[0]
        if op == "=":
            return actual == value
        if op == "in":
            return actual in value
        raise OdooError(500, "builtins.ValueError", f"mock: unsupported operator {op!r}")

    # -- HTTP -----------------------------------------------------------------------------
    def _handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, payload):
                self._send(status, json.dumps(payload).encode(), "application/json; charset=utf-8")

            def do_GET(self):
                mock.requests.append({"path": self.path, "headers": dict(self.headers), "body": b""})
                self._send(200, b"<html>website</html>", "text/html; charset=utf-8")

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                mock.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                if self.path in mock.redirect:
                    return self._send(307, b"", "text/html", {"Location": mock.redirect[self.path]})
                if self.path in mock.fail_once:
                    status, headers = mock.fail_once.pop(self.path)
                    return self._send(status, b"slow down", "text/plain", headers)
                if mock.html_everywhere:
                    return self._send(200, b"<html>website</html>", "text/html; charset=utf-8")
                if self.path == "/web/webclient/version_info":
                    request = json.loads(body)
                    return self._json(200, {"jsonrpc": "2.0", "id": request.get("id"), "result": mock.version_info()})
                if self.path.startswith("/json/2/"):
                    return self._json2(body)
                if self.path.startswith("/xmlrpc/2/"):
                    return self._xmlrpc(body)
                self._send(404, b"<html>not found</html>", "text/html; charset=utf-8")

            def _json2(self, body: bytes):
                if not mock.json2_available:
                    return self._send(404, b"<html>404</html>", "text/html; charset=utf-8")
                auth = self.headers.get("Authorization") or ""
                if auth.lower() != f"bearer {API_KEY}":
                    return self._json(401, {"name": "werkzeug.exceptions.Unauthorized", "message": "Invalid apikey"})
                db = self.headers.get("X-Odoo-Database")
                if db is not None and db != DB:
                    return self._send(404, b"<html>db not found</html>", "text/html; charset=utf-8")
                _, _, _, model, method = self.path.split("/", 4)
                params = json.loads(body)
                if method != "search_read":
                    return self._json(403, {"name": "odoo.exceptions.AccessError", "message": "mock: read only"})
                try:
                    result = mock.search_read(model, **params)
                except OdooError as err:
                    return self._json(err.status, {"name": err.name, "message": err.message})
                self._json(200, result)

            def _xmlrpc(self, body: bytes):
                params, method = xmlrpc.client.loads(body, use_builtin_types=True)
                service = self.path.rsplit("/", 1)[-1]
                try:
                    if service == "common" and method == "authenticate":
                        db, login, key, _ = params
                        result = UID if (db, login, key) == (DB, LOGIN, API_KEY) else False
                    elif service == "object" and method == "execute_kw":
                        db, uid, key, model, orm_method, args, kwargs = params
                        if (db, uid, key) != (DB, UID, API_KEY):
                            raise OdooError(500, "odoo.exceptions.AccessDenied", "Access Denied")
                        if orm_method != "search_read":
                            raise OdooError(500, "odoo.exceptions.AccessError", "mock: read only")
                        result = mock.search_read(model, *args, **kwargs)
                    else:
                        raise OdooError(500, "Exception", f"Method not found: {method}")
                    response = xmlrpc.client.dumps((result,), methodresponse=True, allow_none=True)
                except OdooError as err:
                    fault = xmlrpc.client.Fault(1, f"Traceback (most recent call last):\n  ...\n{err.name}: {err.message}\n")
                    response = xmlrpc.client.dumps(fault, methodresponse=True, allow_none=True)
                self._send(200, response.encode(), "text/xml; charset=utf-8")

        return Handler


def action(id_, code, *, name=None, model="res.partner", usage="ir_actions_server", state="code",
           binding_model_id=False, binding_view_types="list,form", xml_id="", base_automation_id=False):
    return {"id": id_, "name": name or f"Action {id_}", "code": code, "state": state, "model_name": model,
            "usage": usage, "binding_model_id": binding_model_id, "binding_view_types": binding_view_types,
            "xml_id": xml_id, "base_automation_id": base_automation_id}


def modules(*names):
    return [{"id": i, "name": n, "state": "installed"} for i, n in enumerate(("base", *names), 1)]


def schema(models: dict[str, list[str]]):
    ir_model = [{"id": i, "model": m} for i, m in enumerate(models, 1)]
    ir_fields = [{"id": i, "model": m, "name": f}
                 for i, (m, f) in enumerate(((m, f) for m, fs in models.items() for f in fs), 1)]
    return {"ir.model": ir_model, "ir.model.fields": ir_fields}
