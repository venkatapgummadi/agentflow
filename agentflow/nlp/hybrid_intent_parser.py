"""
Hybrid Intent Parser — LLM-first with rule-based fallback.

Combines ``LLMIntentParser`` (for flexible, domain-rich language) with
``IntentParser`` (for deterministic, regulator-friendly fallback).

Design goals (addresses Reviewers 2, 3, 4):

1. **Flexibility** — when an LLM is configured, complex / ambiguous /
   domain-specific phrasing produces a richer plan than the rule parser
   could ever produce on its own.
2. **Determinism** — if the LLM is unavailable, returns degraded
   confidence, or the caller forces ``deterministic=True``, the rule
   parser is used so behaviour stays reproducible (important for SOX /
   HIPAA audit trails).
3. **Cross-validation** — when ``cross_validate=True`` both parsers run
   and their outputs are merged; disagreement lowers the confidence
   score so callers can route to a human or to a more conservative
   plan.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
from typing import Any

from agentflow.nlp.intent_parser import IntentParser
from agentflow.nlp.llm_intent_parser import LLMIntentParser
from agentflow.nlp.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class HybridIntentParser:
    """LLM-first parser with deterministic rule-based fallback."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        rule_parser: IntentParser | None = None,
        llm_parser: LLMIntentParser | None = None,
        confidence_threshold: float = 0.4,
        cross_validate: bool = False,
    ):
        self.rule_parser = rule_parser or IntentParser()
        self.llm_parser = llm_parser or LLMIntentParser(provider=llm_provider)
        self.confidence_threshold = confidence_threshold
        self.cross_validate = cross_validate

    # ── sync convenience ─────────────────────────────────────────────────

    def parse(self, intent: str, deterministic: bool = False) -> dict[str, Any]:
        """Synchronous shortcut. In ``deterministic=True`` only rules run."""
        import asyncio

        if deterministic:
            result = self.rule_parser.parse(intent)
            result["source"] = "rule"
            return result
        try:
            return asyncio.run(self.parse_async(intent))
        except RuntimeError:
            # Already inside an event loop — caller should use parse_async.
            logger.debug("HybridIntentParser.parse called from running loop; using rules")
            result = self.rule_parser.parse(intent)
            result["source"] = "rule"
            return result

    # ── async ────────────────────────────────────────────────────────────

    async def parse_async(self, intent: str, deterministic: bool = False) -> dict[str, Any]:
        rule_result = self.rule_parser.parse(intent)
        rule_result["source"] = "rule"

        if deterministic:
            return rule_result

        llm_result = await self.llm_parser.parse_async(intent)
        if not llm_result.get("operations"):
            logger.info("LLM returned no operations; using rule parser fallback")
            return rule_result

        if self.cross_validate:
            return self._merge(rule_result, llm_result)

        if float(llm_result.get("confidence", 0.0)) >= self.confidence_threshold:
            return llm_result
        return rule_result

    # ── merge / cross-validation ─────────────────────────────────────────

    @staticmethod
    def _merge(rule: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
        """
        Combine rule + LLM outputs. Disagreement reduces the merged
        confidence so callers can decide whether to ask for human review.
        """
        rule_verbs = [op.get("verb") for op in rule.get("operations", [])]
        llm_verbs = [op.get("verb") for op in llm.get("operations", [])]
        agreement = (
            len(set(rule_verbs) & set(llm_verbs)) / max(len(set(rule_verbs) | set(llm_verbs)), 1)
        )

        merged = dict(llm)  # prefer LLM structure
        merged["operations"] = llm.get("operations") or rule.get("operations", [])
        merged["entities"] = {**rule.get("entities", {}), **llm.get("entities", {})}
        merged["conditions"] = (
            list(rule.get("conditions", [])) + list(llm.get("conditions", []))
        )
        merged["confidence"] = round(
            float(llm.get("confidence", 0.0)) * (0.5 + 0.5 * agreement), 3
        )
        merged["source"] = "hybrid"
        merged["agreement"] = round(agreement, 3)
        return merged
