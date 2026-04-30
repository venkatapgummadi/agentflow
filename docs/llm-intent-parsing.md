# LLM-backed Intent Parsing

> **Why this document exists.** Reviewers 2, 3 and 4 noted that the
> rule-based `IntentParser` is brittle on complex / domain-specific
> language. The original choice was deliberate (deterministic =
> auditable for SOX / HIPAA). v1.1 introduces an *additive*
> LLM-backed path with a deterministic fallback so neither use case
> is sacrificed.

## API surface

```python
from agentflow.nlp import (
    IntentParser,           # v1.0, rule-based, deterministic
    LLMIntentParser,        # v1.1, LLM-backed (provider-agnostic)
    HybridIntentParser,     # v1.1, LLM-first with rule fallback
    CallableLLMProvider,    # adapter for any vendor SDK
    DeterministicMockProvider,  # for tests / offline mode
)
```

## Plugging in a real LLM (no AgentFlow dependency on vendor SDKs)

```python
import openai
from agentflow.nlp import (
    HybridIntentParser, LLMIntentParser, CallableLLMProvider,
)

async def call_openai(req):
    resp = await openai.AsyncOpenAI().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": req.system},
            {"role": "user",   "content": req.user},
        ],
        response_format={"type": "json_object"},
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    return resp.choices[0].message.content

provider = CallableLLMProvider(call_openai, name="openai", model="gpt-4o-mini")
parser   = HybridIntentParser(llm_parser=LLMIntentParser(provider=provider))

orchestrator = AgentOrchestrator(intent_parser=parser, connectors=[...])
```

The orchestrator transparently calls `parse_async` if the parser
exposes it, so existing user code does not need to change.

## Compliance: deterministic mode

For audited workflows you can force the rule path:

```python
result = parser.parse(intent, deterministic=True)
assert result["source"] == "rule"
```

This is what the HealthTech pilot in the case study uses by default.

## Cross-validation mode

For high-stakes flows you can run both paths and merge them:

```python
parser = HybridIntentParser(cross_validate=True, ...)
result = await parser.parse_async(intent)
print(result["confidence"], result["agreement"])
```

`agreement < 0.5` is a strong signal to escalate to a human reviewer.
