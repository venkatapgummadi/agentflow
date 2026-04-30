"""
Tests for the AzureAPIMConnector.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio

import pytest

from agentflow.connectors.azure import AzureAPIMConfig, AzureAPIMConnector


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def connector() -> AzureAPIMConnector:
    return AzureAPIMConnector(
        tenant_id="11111111-1111-1111-1111-111111111111",
        subscription_id="22222222-2222-2222-2222-222222222222",
        resource_group="prod-rg",
        service_name="contoso-apim",
        client_id="cid",
        client_secret="secret",
        subscription_key="sk-test",
    )


class TestAzureAPIMConfig:
    def test_gateway_url_is_derived_from_service_name(self):
        cfg = AzureAPIMConfig(service_name="acme-apim")
        assert cfg.gateway_url == "https://acme-apim.azure-api.net"

    def test_management_url_is_derived(self):
        cfg = AzureAPIMConfig(
            subscription_id="sub-42",
            resource_group="rg-42",
            service_name="apim-42",
        )
        assert "subscriptions/sub-42" in cfg.management_url
        assert "resourceGroups/rg-42" in cfg.management_url
        assert "service/apim-42" in cfg.management_url

    def test_custom_management_url_is_preserved(self):
        cfg = AzureAPIMConfig(
            service_name="apim-42",
            management_url="https://example.org/mgmt",
        )
        assert cfg.management_url == "https://example.org/mgmt"


class TestAzureAPIMDiscovery:
    def test_discover_returns_crud_surface(self, connector):
        endpoints = connector.discover()
        # 2 APIs * 3 CRUD methods each = 6 endpoints
        assert len(endpoints) == 6

    def test_discovered_endpoints_have_products_in_tags(self, connector):
        endpoints = connector.discover()
        tag_union = set()
        for ep in endpoints:
            tag_union.update(ep["tags"])
        assert "premium" in tag_union
        assert "standard" in tag_union

    def test_discovery_cache_is_honored(self, connector):
        first = connector.discover()
        second = connector.discover()
        assert first == second
        assert len(connector._api_cache) == 2

    def test_connector_registers_endpoints_on_base(self, connector):
        connector.discover()
        assert len(connector.endpoints) == 6


class TestAzureAPIMInvocation:
    def test_invoke_returns_success_envelope(self, connector):
        connector.discover()
        resp = _run(connector.invoke("customer-api-v1:GET:/customers"))
        assert resp.status_code == 200
        assert resp.body["via"] == "azure-apim"
        assert resp.success is True

    def test_invoke_returns_429_when_rate_limit_exhausted(self, connector):
        op = "customer-api-v1:GET:/customers"
        connector._rate_limits[op] = {"remaining": 0, "reset_at": 9_999_999_999.0}
        resp = _run(connector.invoke(op))
        assert resp.status_code == 429
        assert resp.is_error
        assert resp.retryable


class TestAzureAPIMHealth:
    def test_health_check_true_with_subscription_key(self, connector):
        assert _run(connector.health_check()) is True

    def test_health_check_false_without_credentials(self):
        bare = AzureAPIMConnector(service_name="x")
        assert _run(bare.health_check()) is False

    def test_health_check_true_with_client_id_only(self):
        c = AzureAPIMConnector(service_name="x", client_id="cid")
        assert _run(c.health_check()) is True
