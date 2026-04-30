"""
AgentFlow hello-world.

The smallest possible end-to-end run: parse a natural-language intent
with the v1.1 ``HybridIntentParser``, build an execution plan, execute
it against a stub ``RESTConnector``, and print the result.

Usage::

    pip install -e ".[all]"
    python examples/helloworld.py

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio

from agentflow import AgentOrchestrator, HybridIntentParser, RESTConnector


async def main() -> None:
    # 1. set up an orchestrator with the v1.1 HybridIntentParser.
    #    HybridIntentParser uses the rule-based parser by default
    #    (no LLM provider configured), so this example has no
    #    network dependency.
    orchestrator = AgentOrchestrator(
        intent_parser=HybridIntentParser(),
        connectors=[RESTConnector(base_url="https://api.example.com")],
    )

    # 2. run a natural-language orchestration
    result = await orchestrator.execute(
        "Fetch customer 42 from CRM and create an order if KYC is valid"
    )

    # 3. report what happened
    print("=" * 60)
    print("AgentFlow Hello World")
    print("=" * 60)
    print(f"orchestration_id : {result.context.orchestration_id}")
    print(f"intent           : {result.context.intent}")
    print(f"plan_steps       : {len(result.plan.steps)}")
    for i, step in enumerate(result.plan.steps, 1):
        print(
            f"  step {i}: {step.name:<25}  "
            f"type={step.step_type.value:<10} status={step.status.value}"
        )
    print(f"duration_seconds : {result.duration:.4f}")
    print(f"success          : {result.success}")
    print("=" * 60)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
