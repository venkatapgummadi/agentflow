"""
Tests for the RESTConnector and its auth strategies.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio

import pytest

from agentflow.connectors.rest import (
    ApiKeyAuth,
    BasicAuth,
    BearerTokenAuth,
    NoAuth,
    RESTConnector,
)


def _run(coro):
    """Run a coroutine in a fresh event loop.

    The previous implementation called ``asyncio.get_event_loop()``,
    which fails on Python 3.10+ once a previous async test has closed
    its loop. Using ``asyncio.new_event_loop`` keeps these helpers
    hermetic regardless of test ordering.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


SAMPLE_OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Demo"},
    "paths": {
        "/customers/{id}": {
            "get": {
                "operationId": "getCustomer",
                "summary": "Fetch a customer by id",
                "tags": ["customer", "fetch"],
                "x-latency-p95-ms": 80.0,
                "x-cost-per-call": 0.001,
                "x-rate-limit-rpm": 600,
                "parameters": [{"name": "id", "in": "path"}],
            }
        },
        "/orders": {
            "post": {
                "operationId": "createOrder",
                "summary": "Create an order",
                "tags": ["order", "create"],
            }
        },
    },
}


class TestAuthStrategies:
    def test_no_auth_passes_headers_through(self):
        out = NoAuth().apply({"X-Trace": "abc"})
        assert out == {"X-Trace": "abc"}

    def test_api_key_default_header(self):
        out = ApiKeyAuth("secret").apply({})
        assert out["X-API-Key"] == "secret"

    def test_api_key_custom_header(self):
        out = ApiKeyAuth("secret", header_name="X-Custom").apply({})
        assert out["X-Custom"] == "secret"
        assert "X-API-Key" not in out

    def test_api_key_rejects_empty(self):
        with pytest.raises(ValueError):
            ApiKeyAuth("")

    def test_bearer_sets_authorization(self):
        out = BearerTokenAuth("jwt-token").apply({})
        assert out["Authorization"] == "Bearer jwt-token"

    def test_basic_auth_encoding(self):
        out = BasicAuth("alice", "wonder").apply({})
        # base64("alice:wonder") = "YWxpY2U6d29uZGVy"
        assert out["Authorization"] == "Basic YWxpY2U6d29uZGVy"


class TestRESTConnectorDiscovery:
    def test_discover_registers_endpoints_from_openapi(self):
        rest = RESTConnector(
            base_url="https://api.example.com",
            openapi_spec=SAMPLE_OPENAPI,
        )
        discovered = rest.discover()
        assert len(discovered) == 2
        names = {ep["name"] for ep in discovered}
        assert "getCustomer" in names
        assert "createOrder" in names

    def test_discover_carries_metrics_metadata(self):
        rest = RESTConnector(
            base_url="https://api.example.com",
            openapi_spec=SAMPLE_OPENAPI,
        )
        discovered = rest.discover()
        cust = next(ep for ep in discovered if ep["name"] == "getCustomer")
        assert cust["latency_p95_ms"] == 80.0
        assert cust["cost_per_call"] == 0.001
        assert cust["rate_limit_rpm"] == 600
        assert cust["tags"] == ["customer", "fetch"]

    def test_discover_with_no_spec_returns_empty(self):
        rest = RESTConnector(base_url="https://api.example.com")
        assert rest.discover() == []


class TestRESTConnectorInvoke:
    def test_invoke_fills_path_placeholders(self):
        rest = RESTConnector(
            base_url="https://api.example.com",
            openapi_spec=SAMPLE_OPENAPI,
        )
        resp = _run(rest.invoke("GET /customers/{id}", {"id": "42"}))
        assert resp.success
        assert "customers/42" in rest.call_log[-1]["url"]

    def test_invoke_query_params_for_get(self):
        rest = RESTConnector(base_url="https://api.example.com")
        resp = _run(rest.invoke("GET /search", {"q": "widget"}))
        assert resp.success
        body = rest.call_log[-1]["body"]
        assert body == {"_query": {"q": "widget"}}

    def test_invoke_body_for_post(self):
        rest = RESTConnector(base_url="https://api.example.com")
        resp = _run(rest.invoke("POST /orders", {"sku": "X", "qty": 2}))
        assert resp.success
        assert rest.call_log[-1]["body"] == {"sku": "X", "qty": 2}

    def test_invoke_applies_auth_header(self):
        rest = RESTConnector(
            base_url="https://api.example.com",
            auth=BearerTokenAuth("tk"),
        )
        _run(rest.invoke("GET /me"))
        assert rest.call_log[-1]["headers"]["Authorization"] == "Bearer tk"

    def test_invoke_returns_error_on_4xx(self):
        async def failing(method, url, body, headers, timeout_ms):
            return {"status_code": 404, "body": None, "error_message": "missing"}

        rest = RESTConnector(
            base_url="https://api.example.com",
            http_call=failing,
        )
        resp = _run(rest.invoke("GET /missing"))
        assert resp.is_error
        assert resp.status_code == 404
        assert resp.retryable is False

    def test_invoke_returns_error_on_exception(self):
        async def boom(method, url, body, headers, timeout_ms):
            raise ConnectionError("network down")

        rest = RESTConnector(
            base_url="https://api.example.com",
            http_call=boom,
        )
        resp = _run(rest.invoke("GET /x"))
        assert resp.is_error
        assert resp.retryable is True
        assert "network down" in resp.error_message
