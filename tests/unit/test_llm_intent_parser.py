"""
Tests for the LLM-backed and Hybrid intent parsers.

Uses the bundled ``DeterministicMockProvider`` so the tests are
hermetic and require no network or vendor SDK.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio

import pytest

from agentflow.nlp.hybrid_intent_parser import HybridIntentParser
from agentflow.nlp.intent_parser import IntentParser
from agentflow.nlp.llm_intent_parser import LLMIntentParser
from agentflow.nlp.llm_provider import (
    CallableLLMProvider,
    DeterministicMockProvider,
    LLMRequest,
    LLMResponse,
)


class TestLLMProvider:
    @pytest.mark.asyncio
    async def test_mock_provider_returns_json(self):
        provider = DeterministicMockProvider()
        resp = await provider.complete(
            LLMRequest(system="sys", user="Fetch loan application 4421")
        )
        assert isinstance(resp, LLMResponse)
        payload = resp.as_json()
        assert "operations" in payload
        assert payload["domain_tags"] == ["fintech"]

    @pytest.mark.asyncio
    async def test_callable_provider_wraps_user_function(self):
        async def my_fn(req: LLMRequest) -> str:
            return '{"operations": [{"verb": "fetch", "type": "api_call"}], "confidence": 0.9}'

        provider = CallableLLMProvider(my_fn, name="custom")
        resp = await provider.complete(LLMRequest(system="s", user="u"))
        assert resp.provider == "custom"
        assert resp.as_json()["confidence"] == 0.9


class TestLLMIntentParser:
    @pytest.mark.asyncio
    async def test_parses_with_mock_provider(self):
        parser = LLMIntentParser()
        result = await parser.parse_async(
            "Fetch patient EHR record for member 992 and notify the care team"
        )
        assert result["operations"], "expected at least one operation"
        assert result["confidence"] > 0.0
        assert result["source"].startswith("llm")
        assert "healthtech" in result["domain_tags"]

    @pytest.mark.asyncio
    async def test_empty_intent_returns_zero_confidence(self):
        parser = LLMIntentParser()
        result = await parser.parse_async("   ")
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_provider_failure_falls_through(self):
        class BoomProvider(DeterministicMockProvider):
            async def complete(self, request):  # type: ignore[override]
                raise RuntimeError("network down")

        parser = LLMIntentParser(provider=BoomProvider())
        result = await parser.parse_async("Fetch order 12345")
        assert result["confidence"] == 0.0  # fail closed

    @pytest.mark.asyncio
    async def test_normalizes_step_name_uniqueness(self):
        async def fn(req: LLMRequest) -> str:
            return (
                '{"operations": ['
                '{"name": "step", "verb": "fetch"},'
                '{"name": "step", "verb": "create"}'
                '], "confidence": 0.7}'
            )

        parser = LLMIntentParser(provider=CallableLLMProvider(fn))
        result = await parser.parse_async("do something")
        names = [op["name"] for op in result["operations"]]
        assert len(names) == len(set(names))


class TestHybridIntentParser:
    @pytest.mark.asyncio
    async def test_uses_llm_when_confident(self):
        parser = HybridIntentParser()
        result = await parser.parse_async(
            "Open a fintech loan application for customer 9023"
        )
        assert result["source"].startswith("llm") or result["source"] == "hybrid"

    @pytest.mark.asyncio
    async def test_falls_back_to_rules_when_llm_empty(self):
        async def empty(req: LLMRequest) -> str:
            return "{}"

        parser = HybridIntentParser(llm_parser=LLMIntentParser(provider=CallableLLMProvider(empty)))
        result = await parser.parse_async("Fetch customer 12345")
        assert result["source"] == "rule"

    def test_deterministic_flag_uses_rules_only(self):
        parser = HybridIntentParser()
        result = parser.parse(
            "If credit score > 700 then create a loan application", deterministic=True
        )
        assert result["source"] == "rule"
        assert any(c["type"] in ("if_then", "comparison") for c in result["conditions"])

    @pytest.mark.asyncio
    async def test_cross_validate_lowers_confidence_on_disagreement(self):
        async def disagree(req: LLMRequest) -> str:
            return (
                '{"operations": ['
                '{"verb": "transmute", "type": "api_call"}'
                '], "confidence": 0.95}'
            )

        parser = HybridIntentParser(
            llm_parser=LLMIntentParser(provider=CallableLLMProvider(disagree)),
            cross_validate=True,
        )
        result = await parser.parse_async("Fetch customer 555 and create order")
        assert result["source"] == "hybrid"
        assert result["confidence"] < 0.95
        assert "agreement" in result

    def test_sync_parse_works_outside_loop(self):
        parser = HybridIntentParser()
        result = parser.parse("Fetch order 11 then create shipment")
        assert result["operations"]


def test_rule_parser_still_works_unchanged():
    """Sanity check: existing rule parser behaviour is unchanged."""
    p = IntentParser()
    assert p.parse("Fetch customer 12345")["operations"][0]["verb"] == "fetch"


@pytest.mark.asyncio
async def test_concurrent_calls_are_safe():
    parser = LLMIntentParser()
    intents = [
        "Fetch customer 1",
        "Create loan application",
        "Notify the underwriter",
        "Validate KYC for user 42",
    ]
    results = await asyncio.gather(*[parser.parse_async(i) for i in intents])
    assert all(r["confidence"] > 0 for r in results)


# ── safety guards added in v1.1.2 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_parser_rejects_oversized_intent():
    parser = LLMIntentParser(max_chars=100)
    big = "fetch customer 42 " * 100  # > 100 chars
    result = await parser.parse_async(big)
    assert result["confidence"] == 0.0
    assert result["operations"] == []


@pytest.mark.asyncio
async def test_llm_parser_max_chars_default_is_8000():
    parser = LLMIntentParser()
    assert parser.max_chars == 8000


@pytest.mark.asyncio
async def test_llm_parser_accepts_intent_at_boundary():
    parser = LLMIntentParser(max_chars=200)
    intent = "fetch customer 42 " * 5  # ~90 chars
    result = await parser.parse_async(intent)
    assert result["operations"]
