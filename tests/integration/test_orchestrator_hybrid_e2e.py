"""
End-to-end integration test: AgentOrchestrator + HybridIntentParser
+ stub REST connector + DynamicRouter + ExecutorAgent.

Closes the gap that ``tests/integration/`` was previously empty.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import pytest

from agentflow import (
    AgentOrchestrator,
    HybridIntentParser,
    LLMIntentParser,
    RESTConnector,
)
from agentflow.nlp.llm_provider import CallableLLMProvider, LLMRequest


@pytest.mark.asyncio
async def test_orchestrator_with_default_hybrid_parser():
    parser = HybridIntentParser()
    orch = AgentOrchestrator(
        intent_parser=parser,
        connectors=[RESTConnector(base_url="https://api.example.com")],
    )
    result = await orch.execute(
        "Fetch customer 42 and create an order if KYC passes"
    )
    assert result.success
    assert result.plan.steps, "expected at least one plan step"
    parsed = await result.context.get("intent_parser", "parsed")
    assert parsed["operations"]


@pytest.mark.asyncio
async def test_orchestrator_with_llm_parser_via_callable_provider():
    """The orchestrator must call the LLM path when given an LLM parser."""
    seen: list[str] = []

    async def fake_llm(req: LLMRequest) -> str:
        seen.append(req.user)
        return (
            '{"operations": ['
            '  {"name": "fetch_customer", "verb": "fetch", "type": "api_call",'
            '   "target": "customer 99", "parameters": {"id": "99"},'
            '   "inputs_from": [], "required_tags": ["customer"]}'
            '], "entities": {"numeric_id": ["99"]}, "confidence": 0.9}'
        )

    parser = LLMIntentParser(provider=CallableLLMProvider(fake_llm, name="fake"))
    orch = AgentOrchestrator(
        intent_parser=parser,
        connectors=[RESTConnector(base_url="https://api.example.com")],
    )
    result = await orch.execute("Fetch customer 99 from CRM")
    assert seen == ["Fetch customer 99 from CRM"], "LLM provider must have been called"
    assert result.success
    parsed = await result.context.get("intent_parser", "parsed")
    assert parsed["source"].startswith("llm")


@pytest.mark.asyncio
async def test_orchestrator_falls_back_to_rules_when_llm_returns_empty():
    async def empty_llm(req: LLMRequest) -> str:
        return "{}"

    parser = HybridIntentParser(
        llm_parser=LLMIntentParser(provider=CallableLLMProvider(empty_llm))
    )
    orch = AgentOrchestrator(
        intent_parser=parser,
        connectors=[RESTConnector(base_url="https://api.example.com")],
    )
    result = await orch.execute("Fetch customer 42 and create order")
    parsed = await result.context.get("intent_parser", "parsed")
    assert parsed["source"] == "rule"


@pytest.mark.asyncio
async def test_orchestrator_audit_summary_includes_phases():
    orch = AgentOrchestrator(
        intent_parser=HybridIntentParser(),
        connectors=[RESTConnector(base_url="https://api.example.com")],
    )
    result = await orch.execute("Fetch order 1234")
    summary = result.context.summary()
    # we should at least see plan + execution events
    event_counts = summary.get("event_counts", {})
    assert sum(event_counts.values()) >= 1, f"no events recorded: {summary}"
    assert result.duration > 0
