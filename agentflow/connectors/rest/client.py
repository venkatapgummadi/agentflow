"""
RESTConnector — generic REST/HTTP connector with OpenAPI-driven discovery.

Implements BaseConnector for any HTTP API. Endpoints can be loaded
from an OpenAPI 3.x specification (dict or list-of-paths) or
registered manually. Auth is delegated to an AuthStrategy.

The connector is transport-agnostic: it accepts an injectable
async HTTP function (`http_call`) so it can run with httpx, aiohttp,
or be tested with a stub.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from agentflow.connectors.base import APIEndpoint, APIResponse, BaseConnector
from agentflow.connectors.rest.auth import AuthStrategy, NoAuth

logger = logging.getLogger(__name__)


HttpCall = Callable[
    [str, str, dict[str, Any], dict[str, str], int],
    Awaitable[dict[str, Any]],
]


class RESTConnector(BaseConnector):
    """
    Generic REST connector.

    Args:
        base_url: Root URL for all requests (e.g., "https://api.example.com").
        auth: AuthStrategy instance (defaults to NoAuth).
        openapi_spec: Optional OpenAPI 3.x dict; endpoints will be
            auto-registered from the `paths` section.
        http_call: Injectable async HTTP function. Defaults to a stub
            that records calls (useful for tests / dry-run).
        default_headers: Headers applied to every request.

    Usage:
        rest = RESTConnector(
            base_url="https://api.example.com",
            auth=BearerTokenAuth(token="..."),
            openapi_spec=spec_dict,
        )
        rest.discover()
        resp = await rest.invoke("GET /customers/{id}", {"id": "42"})
    """

    def __init__(
        self,
        base_url: str,
        auth: AuthStrategy | None = None,
        openapi_spec: dict[str, Any] | None = None,
        http_call: HttpCall | None = None,
        default_headers: dict[str, str] | None = None,
        connector_id: str | None = None,
        name: str = "rest",
        config: dict[str, Any] | None = None,
    ):
        super().__init__(connector_id=connector_id, name=name, config=config)
        self.base_url = base_url.rstrip("/")
        self.auth = auth or NoAuth()
        self.openapi_spec = openapi_spec
        self.default_headers = default_headers or {"Accept": "application/json"}
        self._http_call = http_call or _stub_http_call
        self._call_log: list[dict[str, Any]] = []

    def discover(self) -> list[dict[str, Any]]:
        """
        Discover endpoints from the OpenAPI spec.

        Returns a list of endpoint metadata dicts compatible with
        the PlannerAgent and DynamicRouter.
        """
        discovered: list[dict[str, Any]] = []
        if not self.openapi_spec:
            return discovered

        paths = self.openapi_spec.get("paths", {}) or {}
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, op in methods.items():
                if method.lower() not in {
                    "get", "post", "put", "patch", "delete", "head", "options",
                }:
                    continue
                if not isinstance(op, dict):
                    continue

                endpoint = APIEndpoint(
                    name=op.get("operationId") or f"{method.upper()} {path}",
                    method=method.upper(),
                    path=path,
                    description=op.get("summary") or op.get("description") or "",
                    parameters=op.get("parameters", []) or [],
                    tags=[t.lower() for t in (op.get("tags") or [])],
                    latency_p95_ms=float(
                        op.get("x-latency-p95-ms", 100.0)
                    ),
                    cost_per_call=float(op.get("x-cost-per-call", 0.0)),
                    rate_limit_rpm=int(op.get("x-rate-limit-rpm", 1000)),
                )
                self.register_endpoint(endpoint)
                discovered.append(endpoint.to_dict())

        logger.info(
            "RESTConnector '%s' discovered %d endpoints from OpenAPI spec",
            self.name,
            len(discovered),
        )
        return discovered

    async def invoke(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        """
        Execute a REST operation.

        `operation` is "METHOD /path" (e.g., "GET /customers/{id}").
        Path placeholders are filled from `parameters`; unused
        parameters become query params (for GET/DELETE) or JSON body
        (for POST/PUT/PATCH).
        """
        method, _, raw_path = operation.partition(" ")
        method = method.upper().strip()
        path = raw_path.strip()
        params = dict(parameters or {})

        # Fill path placeholders
        used_keys: set[str] = set()
        for key in list(params.keys()):
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(params[key]))
                used_keys.add(key)
        leftover = {k: v for k, v in params.items() if k not in used_keys}

        url = f"{self.base_url}{path}"
        merged_headers = dict(self.default_headers)
        if headers:
            merged_headers.update(headers)
        merged_headers = self.auth.apply(merged_headers)

        body: dict[str, Any]
        if method in {"GET", "DELETE", "HEAD"}:
            # Pass leftovers as query parameters via the http_call payload
            body = {"_query": leftover}
        else:
            body = leftover

        start = time.time()
        self._call_log.append(
            {
                "method": method,
                "url": url,
                "headers": merged_headers,
                "body": body,
                "timeout_ms": timeout_ms,
            }
        )
        try:
            raw = await self._http_call(
                method, url, body, merged_headers, timeout_ms
            )
            latency_ms = (time.time() - start) * 1000.0
            status = int(raw.get("status_code", 200))
            return APIResponse(
                status_code=status,
                body=raw.get("body"),
                headers=raw.get("headers", {}),
                latency_ms=latency_ms,
                connector_id=self.connector_id,
                endpoint_id=raw.get("endpoint_id", ""),
                is_error=status >= 400,
                error_message=raw.get("error_message", "") if status >= 400 else "",
                retryable=status in (408, 429, 500, 502, 503, 504),
            )
        except Exception as exc:  # noqa: BLE001 — surface as APIResponse
            latency_ms = (time.time() - start) * 1000.0
            return APIResponse(
                status_code=0,
                body=None,
                latency_ms=latency_ms,
                connector_id=self.connector_id,
                is_error=True,
                error_message=str(exc),
                retryable=isinstance(exc, (TimeoutError, ConnectionError)),
            )

    async def health_check(self) -> bool:
        """
        Health check via a HEAD/GET on the base URL.

        Returns True on any 2xx/3xx; False otherwise.
        """
        try:
            resp = await self.invoke("GET /", timeout_ms=5000)
            return 200 <= resp.status_code < 400
        except Exception:  # noqa: BLE001
            return False

    @property
    def call_log(self) -> list[dict[str, Any]]:
        """Recorded outgoing calls (useful for tests / audit)."""
        return list(self._call_log)


async def _stub_http_call(
    method: str,
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_ms: int,
) -> dict[str, Any]:
    """
    Default no-network stub. Returns 200 with an echo body.

    Replace by injecting a real `http_call` (httpx, aiohttp, etc.)
    into the connector for production use.
    """
    return {
        "status_code": 200,
        "body": {"echo": {"method": method, "url": url, "body": body}},
        "headers": {"content-type": "application/json"},
    }
