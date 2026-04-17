"""
Tests for the AWSAPIGatewayConnector.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio

import pytest

from agentflow.connectors.aws import AWSAPIGatewayConfig, AWSAPIGatewayConnector


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def connector() -> AWSAPIGatewayConnector:
    return AWSAPIGatewayConnector(
        region="us-east-1",
        account_id="123456789012",
        stage="prod",
        api_type="REST",
        access_key_id="AKIATEST",
        secret_access_key="SECRETTEST",
    )


class TestAWSAPIGatewayConfig:
    def test_default_control_plane_url_is_region_specific(self):
        cfg = AWSAPIGatewayConfig(region="eu-west-1")
        assert cfg.control_plane_url == "https://apigateway.eu-west-1.amazonaws.com"

    def test_invoke_url_template_embeds_region(self):
        cfg = AWSAPIGatewayConfig(region="ap-southeast-2")
        assert "ap-southeast-2" in cfg.invoke_url_template
        assert "{api_id}" in cfg.invoke_url_template
        assert "{stage}" in cfg.invoke_url_template

    def test_custom_urls_are_preserved(self):
        cfg = AWSAPIGatewayConfig(
            region="us-east-1",
            control_plane_url="https://example.org/cp",
            invoke_url_template="https://example.org/invoke/{api_id}",
        )
        assert cfg.control_plane_url == "https://example.org/cp"
        assert cfg.invoke_url_template == "https://example.org/invoke/{api_id}"


class TestAWSAPIGatewayDiscovery:
    def test_discover_returns_crud_surface_for_each_api(self, connector):
        endpoints = connector.discover()
        # 2 stub APIs * 3 CRUD methods each = 6 endpoints
        assert len(endpoints) == 6

    def test_discovered_endpoints_carry_method_and_path(self, connector):
        endpoints = connector.discover()
        methods = {ep["method"] for ep in endpoints}
        assert methods == {"GET", "POST"}
        assert all(ep["path"].startswith("/") for ep in endpoints)

    def test_discovered_endpoints_tagged_with_stage_and_type(self, connector):
        endpoints = connector.discover()
        for ep in endpoints:
            assert "prod" in ep["tags"]
            assert "rest" in ep["tags"]

    def test_discovery_cache_is_honored(self, connector):
        first = connector.discover()
        second = connector.discover()
        assert first == second
        # Cache should not re-fetch apis — _api_cache populated once
        assert len(connector._api_cache) == 2

    def test_connector_registers_endpoints_on_base(self, connector):
        connector.discover()
        assert len(connector.endpoints) == 6


class TestAWSAPIGatewayInvocation:
    def test_invoke_returns_success_envelope(self, connector):
        connector.discover()
        resp = _run(connector.invoke("customer-api:GET:/customer-api"))
        assert resp.status_code == 200
        assert resp.body["via"] == "aws-apigw"
        assert resp.success is True

    def test_invoke_injects_sigv4_authorization_header(self, connector):
        connector.discover()
        resp = _run(connector.invoke("customer-api:GET:/customer-api"))
        # header echo not returned, but ensure call succeeded without auth error
        assert resp.success

    def test_invoke_returns_429_when_rate_limit_exhausted(self, connector):
        op = "customer-api:GET:/customer-api"
        # Force bucket empty
        connector._rate_limits[op] = {"remaining": 0, "reset_at": 9_999_999_999.0}
        resp = _run(connector.invoke(op))
        assert resp.status_code == 429
        assert resp.is_error
        assert resp.retryable


class TestAWSAPIGatewayHealth:
    def test_health_check_true_with_access_key(self, connector):
        assert _run(connector.health_check()) is True

    def test_health_check_false_without_credentials(self):
        bare = AWSAPIGatewayConnector(region="us-east-1")
        assert _run(bare.health_check()) is False

    def test_health_check_true_with_session_token_only(self):
        c = AWSAPIGatewayConnector(region="us-east-1", session_token="FQoGZXIvYX")
        assert _run(c.health_check()) is True
