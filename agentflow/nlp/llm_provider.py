"""
LLM Provider — provider-agnostic interface for intent parsing.

Defines a minimal, narrow contract that any LLM backend (OpenAI,
Anthropic, Azure OpenAI, AWS Bedrock, local Ollama, etc.) can satisfy.
Concrete provider classes live outside the framework so AgentFlow has
no hard dependency on any vendor SDK.

Includes:
- ``LLMProvider``: abstract base class.
- ``DeterministicMockProvider``: zero-dependency provider for tests
  and offline / air-gapped environments.
- ``CallableLLMProvider``: thin adapter around a user-supplied callable
  (e.g. ``lambda prompt: openai_client.chat(...)``) — the recommended
  way to plug in vendor SDKs without importing them here.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """Structured request sent to an LLM provider."""

    system: str
    user: str
    response_format: str = "json"  # "json" | "text"
    max_tokens: int = 1024
    temperature: float = 0.0  # default deterministic
    metadata: dict[str, Any] | None = None


@dataclass
class LLMResponse:
    """Structured response from an LLM provider."""

    text: str
    parsed: dict[str, Any] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    provider: str = ""
    model: str = ""

    def as_json(self) -> dict[str, Any]:
        """Best-effort JSON extraction from the response text."""
        if self.parsed is not None:
            return self.parsed
        return _safe_json_extract(self.text)


class LLMProvider(ABC):
    """Abstract LLM provider used by ``LLMIntentParser``."""

    name: str = "abstract"
    model: str = "unknown"

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Run a single completion. MUST be safe to call concurrently."""


class CallableLLMProvider(LLMProvider):
    """
    Adapter that turns any ``async def fn(LLMRequest) -> str`` into a provider.

    This is the recommended way to integrate a vendor SDK without forcing
    AgentFlow to depend on it::

        async def call_openai(req: LLMRequest) -> str:
            resp = await openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": req.system},
                    {"role": "user", "content": req.user},
                ],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content

        provider = CallableLLMProvider(call_openai, name="openai", model="gpt-4o-mini")
    """

    def __init__(
        self,
        fn: Callable[[LLMRequest], Any],
        name: str = "callable",
        model: str = "user-supplied",
    ):
        self._fn = fn
        self.name = name
        self.model = model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        import asyncio
        import time

        started = time.perf_counter()
        result = self._fn(request)
        if asyncio.iscoroutine(result):
            result = await result
        latency = (time.perf_counter() - started) * 1000
        text = str(result)
        return LLMResponse(
            text=text,
            parsed=_safe_json_extract(text) if request.response_format == "json" else None,
            latency_ms=latency,
            provider=self.name,
            model=self.model,
        )


class DeterministicMockProvider(LLMProvider):
    """
    Zero-dependency provider used by tests and offline mode.

    The mock applies a small set of explicit, auditable rules so that
    unit tests for ``LLMIntentParser`` are stable and reproducible.
    It mirrors the *shape* of a real LLM response but never makes
    a network call. It is intentionally simple — it is **not** meant
    as a substitute for a real LLM in production.
    """

    name = "mock"
    model = "deterministic-v1"

    def __init__(self, scripted: dict[str, dict[str, Any]] | None = None):
        # ``scripted`` lets a test pre-register exact responses keyed by
        # a normalized version of the user prompt.
        self.scripted = scripted or {}

    async def complete(self, request: LLMRequest) -> LLMResponse:
        key = _normalize(request.user)
        if key in self.scripted:
            payload = self.scripted[key]
        else:
            payload = _heuristic_payload(request.user)

        text = json.dumps(payload)
        return LLMResponse(
            text=text,
            parsed=payload,
            tokens_in=len(request.user.split()),
            tokens_out=len(text.split()),
            latency_ms=0.0,
            provider=self.name,
            model=self.model,
        )


# ── helpers ──────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _safe_json_extract(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of ``text``; tolerate prose around it."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _heuristic_payload(prompt: str) -> dict[str, Any]:
    """
    Tiny, deterministic stand-in for a real LLM. It detects a handful of
    enterprise verbs/entities so unit tests can assert on a richer
    structure than the rule parser would produce on its own.
    """
    text = prompt.lower()
    operations: list[dict[str, Any]] = []

    verb_map = [
        ("fetch", ["fetch", "get", "retrieve", "lookup", "read"]),
        ("create", ["create", "open", "submit", "register", "post"]),
        ("update", ["update", "patch", "modify"]),
        ("notify", ["notify", "alert", "email", "page"]),
        ("validate", ["validate", "verify", "check"]),
        ("enrich", ["enrich", "augment", "join"]),
    ]
    for canonical, surface in verb_map:
        for token in surface:
            if re.search(rf"\b{token}\b", text):
                operations.append({"verb": canonical, "surface": token})
                break

    domains = []
    for tag, kws in {
        "fintech": ["loan", "credit", "kyc", "transaction", "ach", "settlement"],
        "healthtech": ["patient", "fhir", "icd", "ehr", "claim"],
        "ecommerce": ["order", "cart", "sku", "fulfillment", "shipment"],
        "insurance": ["policy", "premium", "claim", "underwriting"],
    }.items():
        if any(k in text for k in kws):
            domains.append(tag)

    return {
        "operations": operations,
        "domain_tags": domains,
        "confidence": 0.85 if operations else 0.3,
        "source": "deterministic-mock",
    }
