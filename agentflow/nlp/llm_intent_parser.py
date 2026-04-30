"""
LLM-backed Intent Parser.

A drop-in replacement / augmentation for ``IntentParser`` that calls
out to a pluggable ``LLMProvider`` to extract a structured workflow
from natural language. Designed to:

* preserve the *output schema* of the rule-based parser so downstream
  code (Planner, Executor) does not need to change,
* fail closed: if the LLM is unavailable, returns an empty result with
  ``confidence=0.0`` so a caller (e.g. ``HybridIntentParser``) can fall
  back to the rule parser deterministically,
* never import any vendor SDK at module import time.

This module addresses Reviewer 2/3/4 concerns about the lack of
LLM-grade NLP capability, while preserving the deterministic /
compliance-friendly path that motivated the original rule parser.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
from typing import Any

from agentflow.nlp.intent_parser import ParsedIntent
from agentflow.nlp.llm_provider import (
    DeterministicMockProvider,
    LLMProvider,
    LLMRequest,
)

logger = logging.getLogger(__name__)


_DEFAULT_SYSTEM = """You are an enterprise API orchestration intent parser.

Decompose the user request into a JSON object with this exact schema:

{
  "operations": [
    {
      "name": "<unique_step_name>",
      "type": "api_call | transform | condition | aggregate",
      "verb": "<canonical verb such as fetch|create|update|delete|notify|validate|enrich>",
      "target": "<noun phrase, e.g. 'customer 12345'>",
      "parameters": { "<key>": "<value>" },
      "inputs_from": ["<earlier step name>"],
      "required_tags": ["<capability tag>"]
    }
  ],
  "entities": { "<entity_type>": ["<value>", ...] },
  "conditions": [
    { "type": "comparison", "field": "<name>", "operator": ">|<|>=|<=|==|!=", "value": <number> }
  ],
  "domain_tags": ["fintech | healthtech | ecommerce | insurance | other"]
}

Rules:
- Use only the listed types and operators.
- Step names MUST be unique and snake_case.
- Output JSON only — no prose, no markdown fences."""


class LLMIntentParser:
    """
    Parses intents using an LLM provider.

    Usage::

        from agentflow.nlp.llm_intent_parser import LLMIntentParser
        from agentflow.nlp.llm_provider import CallableLLMProvider

        provider = CallableLLMProvider(my_async_openai_call, name="openai")
        parser = LLMIntentParser(provider=provider)
        result = await parser.parse_async(
            "Open a high-priority loan application for member 4421 if "
            "credit score is above 720 and notify the underwriting team."
        )
    """

    # Default safe upper bound on user-supplied intent length. Anything
    # longer is almost certainly an error or an abuse vector (denial-of-wallet
    # against the LLM provider, context-window overflow, prompt injection
    # padding). Callers can raise this with ``max_chars=`` if they have a
    # legitimate reason.
    DEFAULT_MAX_CHARS = 8_000

    def __init__(
        self,
        provider: LLMProvider | None = None,
        system_prompt: str = _DEFAULT_SYSTEM,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        max_chars: int | None = None,
    ):
        self.provider = provider or DeterministicMockProvider()
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_chars = max_chars if max_chars is not None else self.DEFAULT_MAX_CHARS

    async def parse_async(self, intent: str) -> dict[str, Any]:
        """Async entry-point. Returns the same schema as ``IntentParser.parse``."""
        if not intent or not intent.strip():
            return ParsedIntent(confidence=0.0).to_dict()

        # Guard against runaway-size intents before hitting the provider.
        if len(intent) > self.max_chars:
            logger.warning(
                "Intent length %d exceeds max_chars=%d; refusing to call LLM provider",
                len(intent),
                self.max_chars,
            )
            return ParsedIntent(raw_intent=intent[: self.max_chars], confidence=0.0).to_dict()

        request = LLMRequest(
            system=self.system_prompt,
            user=intent,
            response_format="json",
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        try:
            response = await self.provider.complete(request)
        except Exception as exc:  # noqa: BLE001 - we want to fail closed
            logger.warning("LLM provider %s failed: %s", self.provider.name, exc)
            return ParsedIntent(raw_intent=intent, confidence=0.0).to_dict()

        payload = response.as_json()
        return self._normalize(intent, payload, response_provider=response.provider)

    # ── normalization ────────────────────────────────────────────────────

    def _normalize(
        self,
        intent: str,
        payload: dict[str, Any],
        response_provider: str = "",
    ) -> dict[str, Any]:
        """Coerce LLM output into the canonical AgentFlow intent schema."""
        if not isinstance(payload, dict) or not payload:
            return ParsedIntent(raw_intent=intent, confidence=0.0).to_dict()

        raw_ops = payload.get("operations") or []
        operations: list[dict[str, Any]] = []
        used_names: set[str] = set()
        for i, op in enumerate(raw_ops):
            if not isinstance(op, dict):
                continue
            name = str(op.get("name") or f"step_{i}")
            # ensure uniqueness
            base = name
            n = 1
            while name in used_names:
                n += 1
                name = f"{base}_{n}"
            used_names.add(name)

            op_type = str(op.get("type") or "api_call")
            if op_type not in {"api_call", "transform", "condition", "aggregate"}:
                op_type = "api_call"

            operations.append(
                {
                    "name": name,
                    "type": op_type,
                    "verb": str(op.get("verb") or "execute"),
                    "target": str(op.get("target") or ""),
                    "raw_clause": str(op.get("raw_clause") or intent),
                    "parameters": dict(op.get("parameters") or {}),
                    "inputs_from": list(op.get("inputs_from") or []),
                    "required_tags": list(op.get("required_tags") or []),
                }
            )

        entities = payload.get("entities") or {}
        if not isinstance(entities, dict):
            entities = {}
        entities = {str(k): [str(v) for v in (vs or [])] for k, vs in entities.items()}

        conditions: list[dict[str, Any]] = []
        for cond in payload.get("conditions") or []:
            if not isinstance(cond, dict):
                continue
            conditions.append(cond)

        confidence = float(payload.get("confidence", 0.0) or 0.0)
        if confidence == 0.0 and operations:
            # If the model didn't set a confidence, derive a conservative one.
            confidence = min(1.0, 0.5 + 0.1 * len(operations))

        result = ParsedIntent(
            raw_intent=intent,
            operations=operations,
            entities=entities,
            conditions=conditions,
            confidence=confidence,
        ).to_dict()
        result["domain_tags"] = list(payload.get("domain_tags") or [])
        result["source"] = f"llm:{response_provider}" if response_provider else "llm"
        return result
