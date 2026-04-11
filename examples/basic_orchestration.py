"""
Example: Basic API Orchestration with AgentFlow.

Demonstrates how to set up the orchestrator with a MuleSoft connector
and execute a natural-language workflow.

Author: Venkata Pavan Kumar Gummadi
"""

import asyncio
import json

from agentflow import AgentOrchestrator, MuleSoftConnector
from agentflow.routing.dynamic_router import DynamicRouter, RoutingWeights


async def main():
    # 1. Configure MuleSoft connector
    mulesoft = MuleSoftConnector(
        anypoint_url="https://anypoint.mulesoft.com",
        org_id="demo-org-id",
        environment="sandbox",
        client_id="your-client-id",
        client_secret="your-client-secret",
    )

    # 2. Configure intelligent router (prioritize low latency)
    router = DynamicRouter(weights=RoutingWeights.low_latency())

    # 3. Initialize the orchestrator
    orchestrator = AgentOrchestrator(
        connectors=[mulesoft],
        router=router,
        max_parallel_steps=5,
    )

    # 4. Execute a natural-language orchestration
    result = await orchestrator.execute(
        intent=(
            "Fetch customer 12345 from CRM, enrich with credit score, "
            "and create a loan application if score > 700"
        ),
        parameters={"customer_id": "12345", "min_credit_score": 700},
    )

    # 5. Inspect results
    print("Orchestration Result:")
    print(json.dumps(result.to_dict(), indent=2, default=str))

    print(f"\nSuccess: {result.success}")
    print(f"Duration: {result.duration:.2f}s")
    print(f"Steps executed: {len(result.plan.steps)}")

    # 6. Audit trail
    print("\nAudit Journal:")
    for event in result.context.journal:
        print(f"  [{event.event_type.value}] {event.message}")


if __name__ == "__main__":
    asyncio.run(main())
