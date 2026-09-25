"""sevlint remote: lint the server action code stored in a live Odoo database, read-only.

What is read: the server version (the unauthenticated ``/web/webclient/version_info``) and
``search_read`` on ir.module.module, ir.actions.server, ir.cron, base.automation, ir.model and
ir.model.fields, through JSON-2 (Odoo 19+) or XML-RPC (17.0-18.x). The client refuses any
other method, so nothing can be written. The API key comes from an environment variable, the
keyring or a prompt (never from the command line), goes only to the given host (redirects
are refused, plain http only to localhost) and never appears in any output.
"""
from __future__ import annotations

import ast
import getpass
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xmlrpc.client
from dataclasses import dataclass, field
from pathlib import Path
from xml.parsers.expat import ExpatError

from . import __version__, fields, profile as profiles, sources
from .linter import Options, Report, _lint_into

READ_METHODS = frozenset({"search_read"})  # the only model method sevlint ever calls
PAGE = 200
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DEFAULT_KEY_ENV = "ODOO_API_KEY"
KEYRING_SERVICE = "sevlint"
USAGE_CALLER = {"ir_cron": "cron", "base_automation": "automation"}
PROTOCOLS = ("auto", "json2", "xmlrpc")
MAX_RETRIES = 3


class RemoteError(Exception):
    """A connection, authentication or protocol problem (exit code 2)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib would replay the Authorization header to wherever the server points.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RemoteError(f"{req.full_url} redirects to {newurl}; pass that URL instead "
                          f"(sevlint does not follow redirects with credentials)")


def parse_url(url: str, allow_http: bool = False) -> str:
    """The server's base URL: 'mycompany.odoo.com' or a URL copied from the browser
    ('https://mycompany.odoo.com/odoo/action-12') -> 'https://mycompany.odoo.com'."""
    url = url.strip()
    parsed = urllib.parse.urlsplit(url if "://" in url else f"https://{url}")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RemoteError(f"not an http(s) URL: {url!r}")
    if parsed.username or parsed.password:
        raise RemoteError("credentials in the URL are not accepted; put the API key in the environment "
                          f"variable {DEFAULT_KEY_ENV} (or the one --api-key-env names)")
    if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS and not allow_http:
        raise RemoteError(f"refusing to send an API key over plain http to {parsed.hostname}; use https "
                          f"(or --allow-http for a trusted network)")
    return f"{parsed.scheme}://{parsed.netloc}"  # Odoo is served from the root, not a sub-path


class Transport:
    """POSTs to one server: no redirects, a request interval (Odoo Online allows about one
    request per second), retries on 429/503, and the API key redacted from every error."""

    def __init__(self, base: str, *, timeout: float = 30.0, min_interval: float | None = None,
                 opener: urllib.request.OpenerDirector | None = None):
        self.base = base
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(_NoRedirect)
        host = urllib.parse.urlsplit(base).hostname or ""
        self.min_interval = (1.0 if host.endswith(".odoo.com") else 0.0) if min_interval is None else min_interval
        self.secret: str | None = None
        self._last = 0.0

    @property
    def host(self) -> str:
        return urllib.parse.urlsplit(self.base).hostname or self.base

    def redact(self, text: str) -> str:
        return text.replace(self.secret, "***") if self.secret else text

    def post(self, path: str, body: bytes, headers: dict[str, str]) -> tuple[int, str, bytes]:
        """(status, content type, body); HTTP errors are returned, network errors raised."""
        for attempt in range(MAX_RETRIES + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            request = urllib.request.Request(self.base + path, data=body, method="POST",
                                             headers={"User-Agent": f"sevlint/{__version__}", **headers})
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    return response.status, response.headers.get_content_type(), response.read()
            except urllib.error.HTTPError as err:
                data = err.read()
                if err.code in (429, 503) and attempt < MAX_RETRIES:
                    time.sleep(_retry_after(err.headers.get("Retry-After") if err.headers else None, attempt))
                    continue
                return err.code, err.headers.get_content_type() if err.headers else "", data
            except (urllib.error.URLError, OSError, http.client.HTTPException) as err:
                reason = getattr(err, "reason", None) or err
                raise RemoteError(self.redact(f"cannot reach {self.base}: {reason}")) from None
            finally:
                self._last = time.monotonic()
        raise AssertionError("unreachable")


def _retry_after(value: str | None, attempt: int) -> float:
    try:
        return min(max(float(value), 0.0), 30.0) if value else 2.0 ** (attempt + 1)
    except ValueError:
        return 2.0 ** (attempt + 1)


@dataclass(frozen=True)
class ServerInfo:
    series: str  # normalized, e.g. '19.0' or 'saas-19.2'
    version: str  # as the server reports it, e.g. 'saas~19.2+e'
    enterprise: bool


def server_version(transport: Transport) -> ServerInfo:
    body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}, "id": 1}).encode()
    status, ctype, data = transport.post("/web/webclient/version_info", body, {"Content-Type": "application/json"})
    try:
        result = json.loads(data)["result"] if status == 200 and ctype == "application/json" else None
        series = str(result["server_serie"])
    except (ValueError, KeyError, TypeError):
        raise RemoteError(f"{transport.base} does not answer like an Odoo server "
                          f"(version_info: HTTP {status}, {ctype or 'no content type'})") from None
    info = result.get("server_version_info") or []
    return ServerInfo(profiles.normalize_version(series), str(result.get("server_version", series)),
                      len(info) > 5 and info[5] == "e")


def _paged(fetch) -> list[dict]:
    out: list[dict] = []
    while True:
        batch = fetch(len(out))
        if not isinstance(batch, list):
            raise RemoteError(f"unexpected search_read result: {type(batch).__name__}")
        out += batch
        if len(batch) < PAGE:
            return out


def _only_reads(model: str, method: str) -> None:
    if method not in READ_METHODS:
        raise RemoteError(f"refusing to call {model}.{method}: sevlint only reads")


class Json2Client:
    """Odoo 19+: POST /json/2/<model>/<method>, bearer API key."""
    protocol = "JSON-2"

    def __init__(self, transport: Transport, db: str | None, key: str):
        self.transport, self.db, self._key = transport, db, key

    def call(self, model: str, method: str, **params):
        _only_reads(model, method)
        headers = {"Authorization": f"bearer {self._key}", "Content-Type": "application/json; charset=utf-8"}
        if self.db:
            headers["X-Odoo-Database"] = self.db
        status, ctype, data = self.transport.post(f"/json/2/{model}/{method}", json.dumps(params).encode(), headers)
        payload = None
        if ctype == "application/json":
            try:
                payload = json.loads(data)
            except ValueError:
                pass
        if status == 200 and ctype == "application/json":
            return payload
        message = payload.get("message") if isinstance(payload, dict) else None
        if status == 401:
            raise RemoteError("authentication failed: check the API key (and --db on a multi-database server)")
        if status == 404 and message is None:
            where = f" for database {self.db!r}" if self.db else ""
            raise RemoteError(f"{self.transport.base} has no JSON-2 endpoint{where} (Odoo 19+ only: use --protocol "
                              f"xmlrpc before; or check --db)")
        if status == 403:
            raise RemoteError(self.transport.redact(f"{model}.{method}: access denied ({message or 'HTTP 403'}); the "
                                                    f"API key's user needs Administration / Settings"))
        if status == 200:
            raise RemoteError(f"{model}.{method}: expected JSON, got {ctype or 'no content type'}")
        raise RemoteError(self.transport.redact(f"{model}.{method}: HTTP {status}: {message or 'no details'}"))

    def search_read(self, model: str, domain: list, field_names: list[str], context: dict | None = None) -> list[dict]:
        return _paged(lambda offset: self.call(model, "search_read", domain=domain, fields=field_names,
                                               offset=offset, limit=PAGE, order="id", context=context or {}))


class XmlRpcClient:
    """Odoo 17.0-18.x (deprecated from 19.0): /xmlrpc/2/common + /xmlrpc/2/object."""
    protocol = "XML-RPC"

    def __init__(self, transport: Transport, db: str, login: str, key: str):
        self.transport, self.db, self._key = transport, db, key
        self.uid = self._rpc("common", "authenticate", db, login, key, {})
        if not self.uid:
            raise RemoteError("authentication failed: check --user (the API key's login), --db and the API key")

    def _rpc(self, service: str, method: str, *params):
        body = xmlrpc.client.dumps(params, method, allow_none=True).encode()
        status, ctype, data = self.transport.post(f"/xmlrpc/2/{service}", body, {"Content-Type": "text/xml"})
        if status != 200:
            raise RemoteError(f"{self.transport.base} has no XML-RPC endpoint (HTTP {status})" if status == 404
                              else f"XML-RPC {service}.{method}: HTTP {status}")
        try:
            (result,), _ = xmlrpc.client.loads(data, use_builtin_types=True)
        except xmlrpc.client.Fault as fault:
            lines = [line for line in str(fault.faultString).splitlines() if line.strip()]
            raise RemoteError(self.transport.redact(f"XML-RPC {service}.{method}: {lines[-1] if lines else fault.faultCode}")) from None
        except (ExpatError, ValueError, xmlrpc.client.ResponseError):
            raise RemoteError(f"XML-RPC {service}.{method}: not an XML-RPC response ({ctype or 'no content type'})") from None
        return result

    def search_read(self, model: str, domain: list, field_names: list[str], context: dict | None = None) -> list[dict]:
        _only_reads(model, "search_read")
        return _paged(lambda offset: self._rpc(
            "object", "execute_kw", self.db, self.uid, self._key, model, "search_read", [domain],
            {"fields": field_names, "offset": offset, "limit": PAGE, "order": "id", "context": context or {}}))


def api_key(env_var: str, host: str, *, interactive: bool | None = None) -> str:
    """The API key from ``env_var``, else the keyring (service 'sevlint', user = host), else a prompt."""
    key = os.environ.get(env_var, "").strip()
    if key:
        return key
    try:
        import keyring  # optional dependency
        key = (keyring.get_password(KEYRING_SERVICE, host) or "").strip()
    except Exception:  # noqa: BLE001 - not installed, or no usable backend
        key = ""
    if key:
        return key
    if interactive is None:
        interactive = all(stream is not None and stream.isatty() for stream in (sys.stdin, sys.stderr))
    if interactive:
        key = getpass.getpass(f"API key for {host} (input hidden): ").strip()
    if not key:
        raise RemoteError(f"no API key: set {env_var} (or `keyring set {KEYRING_SERVICE} {host}`); an API key is "
                          f"created under Preferences > Account Security > New API Key")
    return key


def connect(transport: Transport, info: ServerInfo, *, protocol: str, db: str | None, login: str | None,
            key: str):
    transport.secret = key
    if protocol == "auto":
        protocol = "json2" if profiles.version_key(info.series) >= (19, 0) else "xmlrpc"
    if protocol == "json2":
        return Json2Client(transport, db, key)
    if not db or not login:
        raise RemoteError(f"XML-RPC (Odoo {info.series}) needs --db and --user (the API key's login)")
    return XmlRpcClient(transport, db, login, key)


@dataclass
class RemoteAction:
    id: int
    name: str
    code: str
    model: str | None
    caller: str
    binding: str | None
    xml_id: str = ""
    active: bool = True

    @property
    def path(self) -> str:
        return f"ir.actions.server/{self.id}"

    @property
    def label(self) -> str:
        return f"{self.name!r}" + (f" {self.xml_id}" if self.xml_id else "") + ("" if self.active else " (archived)")


@dataclass
class Snapshot:
    modules: frozenset[str]
    actions: list[RemoteAction] = field(default_factory=list)


def _m2o_id(value) -> int | None:
    return value[0] if isinstance(value, (list, tuple)) and value else None


def fetch(client, ids: list[int] | None = None) -> Snapshot:
    modules = frozenset(r["name"] for r in client.search_read("ir.module.module", [["state", "=", "installed"]],
                                                              ["name"]))
    domain = [["state", "=", "code"]] + ([["id", "in", ids]] if ids else [])
    wanted = ["name", "code", "model_name", "usage", "binding_model_id", "binding_view_types", "xml_id"]
    automations = "base_automation" in modules
    if automations:
        wanted.append("base_automation_id")
    rows = client.search_read("ir.actions.server", domain, wanted, {"active_test": False})
    inactive: set[int] = set()
    for cron in client.search_read("ir.cron", [["active", "=", False]], ["ir_actions_server_id"],
                                   {"active_test": False}):
        inactive.add(_m2o_id(cron["ir_actions_server_id"]))
    archived_rules: set[int] = set()
    if automations:
        archived_rules = {r["id"] for r in client.search_read("base.automation", [["active", "=", False]], ["id"],
                                                              {"active_test": False})}
    actions = []
    for row in rows:
        code = row.get("code") or ""
        if not code.strip():
            continue
        caller = USAGE_CALLER.get(row.get("usage"), "server_action")
        active = row["id"] not in inactive and _m2o_id(row.get("base_automation_id")) not in archived_rules
        actions.append(RemoteAction(
            id=row["id"], name=str(row.get("name") or ""), code=code, model=row.get("model_name") or None,
            caller=caller, binding=(row.get("binding_view_types") or None) if row.get("binding_model_id") else None,
            xml_id=row.get("xml_id") or "", active=active))
    return Snapshot(modules, actions)


def fetch_schema(client, models: set[str]) -> fields.LiveSchema:
    """The database's view of the models the code uses (installed or not, and their fields)."""
    wanted = sorted(models)
    if not wanted:
        return fields.LiveSchema(frozenset())
    installed = {r["model"] for r in client.search_read("ir.model", [["model", "in", wanted]], ["model"])}
    by_model: dict[str, set[str]] = {m: set() for m in installed}
    if installed:
        for row in client.search_read("ir.model.fields", [["model", "in", sorted(installed)]], ["model", "name"]):
            by_model.setdefault(row["model"], set()).add(row["name"])
    return fields.LiveSchema(frozenset(installed), {m: frozenset(f) for m, f in by_model.items()})


def models_used(actions: list[RemoteAction]) -> set[str]:
    out: set[str] = set()
    for action in actions:
        try:
            tree = ast.parse(action.code.strip())
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            continue
        out |= fields.referenced_models(tree, action.model)
    return out


def lint(snapshot: Snapshot, version: str, opts: Options, schema: fields.LiveSchema | None) -> Report:
    report = Report()
    for action in snapshot.actions:
        snippet = sources.Snippet(path=action.path, code=action.code, first_line=1, caller=action.caller,
                                  odoo_version=version, label=action.label, modules=snapshot.modules,
                                  binding=action.binding, model=action.model)
        _lint_into(report, snippet, opts, version, schema)
    return report


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "action"


def dump(snapshot: Snapshot, version: str, directory: Path) -> list[Path]:
    """Write each action's code as DIR/<id>_<name>.py with a sevlint header (for `sevlint check`)."""
    directory.mkdir(parents=True, exist_ok=True)
    context_modules = {m for providers in profiles.load(version).context_addons.values() for m in providers}
    modules = sorted(snapshot.modules & context_modules)
    written = []
    for action in snapshot.actions:
        header = [f"odoo={version}", f"caller={action.caller}"]
        if action.model:
            header.append(f"model={action.model}")
        if modules:
            header.append(f"modules={','.join(modules)}")
        if action.binding:
            header.append(f"binding={action.binding.replace(' ', '')}")
        path = directory / f"{action.id}_{_slug(action.name)}.py"
        path.write_text(f"# {action.path} {action.label}\n# sevlint: {' '.join(header)}\n{action.code.strip()}\n",
                        encoding="utf-8")
        written.append(path)
    return written
