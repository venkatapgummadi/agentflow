"""
GraphQLConnector — schema-introspection-driven GraphQL connector.

Implements BaseConnector for GraphQL endpoints. Each root-level Query
or Mutation field is registered as an APIEndpoint, allowing the
PlannerAgent and DynamicRouter to treat GraphQL operations the same
as REST endpoints.

The transport is injectable (`gql_call`) so this works with httpx,
aiohttp, gql, or a test stub.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from agentflow.connectors.base import APIEndpoint, APIResponse, BaseConnector

logger = logging.getLogger(__name__)


GqlCall = Callable[
    [str, str, dict[str, Any], dict[str, str], int],
    Awaitable[dict[str, Any]],
]


class GraphQLConnector(BaseConnector):
    """
    GraphQL connector with introspection-based discovery.

    Args:
        endpoint_url: Single GraphQL HTTP endpoint.
        schema: Pre-fetched introspection schema (dict). The shape
            expected mirrors the standard introspection response,
            but a simplified shape is also accepted::

                {
                    "queries": [{"name": "...", "description": "...", "tags": [...]}],
                    "mutations": [{"name": "...", "description": "...", "tags": [...]}],
                }

        gql_call: Injectable async HTTP function for executing
            GraphQL queries.
        headers: Default headers (e.g., Authorization).

    Usage:
        gql = GraphQLConnector(
            endpoint_url="https://api.example.com/graphql",
            schema=schema_dict,
        )
        gql.discover()
        resp = await gql.invoke("query getUser", {"id": "42"})
    """

    def __init__(
        self,
        endpoint_url: str,
        schema: dict[str, Any] | None = None,
        gql_call: GqlCall | None = None,
        headers: dict[str, str] | None = None,
        connector_id: str | None = None,
        name: str = "graphql",
        config: dict[str, Any] | None = None,
    ):
        super().__init__(connector_id=connector_id, name=name, config=config)
        self.endpoint_url = endpoint_url
        self.schema = schema or {}
        self.headers = headers or {"Content-Type": "application/json"}
        self._gql_call = gql_call or _stub_gql_call
        self._call_log: list[dict[str, Any]] = []

    def discover(self) -> list[dict[str, Any]]:
        """Register endpoints from the introspected schema."""
        discovered: list[dict[str, Any]] = []

        ops = self._extract_operations(self.schema)
        for op_type, items in ops.items():  # op_type: "query" | "mutation"
            for item in items:
                op_name = item.get("name", "")
                if not op_name:
                    continue
                endpoint = APIEndpoint(
                    name=f"{op_type} {op_name}",
                    method="POST",
                    path="/graphql",
                    description=item.get("description") or "",
                    parameters=item.get("args", []) or [],
                    tags=[t.lower() for t in (item.get("tags") or [])] + [op_type],
                    latency_p95_ms=float(item.get("latency_p95_ms", 120.0)),
                    cost_per_call=float(item.get("cost_per_call", 0.0)),
                    rate_limit_rpm=int(item.get("rate_limit_rpm", 1000)),
                )
                self.register_endpoint(endpoint)
                discovered.append(endpoint.to_dict())

        logger.info(
            "GraphQLConnector '%s' discovered %d operations",
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
        Execute a GraphQL operation.

        `operation` is "<type> <name>" (e.g., "query getUser").
        `parameters` becomes the GraphQL `variables` map.
        """
        op_type, _, op_name = operation.partition(" ")
        op_type = op_type.lower().strip()
        op_name = op_name.strip()
        if op_type not in {"query", "mutation"}:
            return APIResponse(
                status_code=400,
                is_error=True,
                error_message=(
                    f"Unsupported GraphQL operation type: {op_type!r} "
                    "(expected 'query' or 'mutation')"
                ),
                connector_id=self.connector_id,
            )

        gql_doc = self._build_document(op_type, op_name, parameters or {})
        merged_headers = dict(self.headers)
        if headers:
            merged_headers.update(headers)

        start = time.time()
        self._call_log.append(
            {
                "endpoint_url": self.endpoint_url,
                "document": gql_doc,
                "variables": parameters or {},
                "headers": merged_headers,
            }
        )
        try:
            raw = await self._gql_call(
                self.endpoint_url,
                gql_doc,
                parameters or {},
                merged_headers,
                timeout_ms,
            )
            latency_ms = (time.time() - start) * 1000.0
            data = raw.get("data")
            errors = raw.get("errors") or []
            status = int(raw.get("status_code", 200))
            is_error = bool(errors) or status >= 400
            return APIResponse(
                status_code=200 if not is_error else (status or 500),
                body={"data": data, "errors": errors} if errors else data,
                headers=raw.get("headers", {}),
                latency_ms=latency_ms,
                connector_id=self.connector_id,
                is_error=is_error,
                error_message=(errors[0].get("message", "") if errors else ""),
                retryable=is_error and status in (0, 408, 429, 500, 502, 503, 504),
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.time() - start) * 1000.0
            return APIResponse(
                status_code=0,
                latency_ms=latency_ms,
                connector_id=self.connector_id,
                is_error=True,
                error_message=str(exc),
                retryable=isinstance(exc, (TimeoutError, ConnectionError)),
            )

    @property
    def call_log(self) -> list[dict[str, Any]]:
        """Recorded outgoing calls (useful for tests / audit)."""
        return list(self._call_log)

    async def health_check(self) -> bool:
        """Health check via a trivial introspection query."""
        try:
            doc = "{ __typename }"
            resp = await self._gql_call(
                self.endpoint_url, doc, {}, self.headers, 5000
            )
            return not resp.get("errors") and resp.get("data") is not None
        except Exception:  # noqa: BLE001
            return False

    # ── Internal Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _extract_operations(schema: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Normalize multiple schema shapes into queries/mutations lists."""
        if "queries" in schema or "mutations" in schema:
            return {
                "query": list(schema.get("queries") or []),
                "mutation": list(schema.get("mutations") or []),
            }

        # Standard introspection shape: __schema.queryType.fields, etc.
        out: dict[str, list[dict[str, Any]]] = {"query": [], "mutation": []}
        root = schema.get("__schema") or schema
        for op_type, key in (("query", "queryType"), ("mutation", "mutationType")):
            type_def = root.get(key) or {}
            for field in type_def.get("fields", []) or []:
                out[op_type].append(
                    {
                        "name": field.get("name", ""),
                        "description": field.get("description", ""),
                        "args": field.get("args", []) or [],
                        "tags": field.get("tags", []) or [],
                    }
                )
        return out

    @staticmethod
    def _build_document(
        op_type: str, op_name: str, variables: dict[str, Any]
    ) -> str:
        """
        Build a minimal GraphQL document.

        For a real production connector you would compose selection
        sets from the schema. Here we emit a generic document that
        delegates field selection to an explicit `_selection` variable
        when provided, defaulting to `id`.
        """
        selection = variables.pop("_selection", "id") if isinstance(variables, dict) else "id"
        if variables:
            var_decls = ", ".join(f"${k}: JSON" for k in variables)
            args = ", ".join(f"{k}: ${k}" for k in variables)
            return (
                f"{op_type} {op_name}Op({var_decls}) {{ "
                f"{op_name}({args}) {{ {selection} }} }}"
            )
        return f"{op_type} {op_name}Op {{ {op_name} {{ {selection} }} }}"


async def _stub_gql_call(
    endpoint_url: str,
    document: str,
    variables: dict[str, Any],
    headers: dict[str, str],
    timeout_ms: int,
) -> dict[str, Any]:
    """Default no-network stub returning a successful echo response."""
    return {
        "status_code": 200,
        "data": {"echo": {"document": document, "variables": variables}},
        "errors": [],
        "headers": {"content-type": "application/json"},
    }
