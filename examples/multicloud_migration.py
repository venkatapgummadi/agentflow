"""
Example: Multi-Cloud API Migration and Traffic Shifting.

Demonstrates AgentFlow managing a zero-downtime API migration from
on-premise MuleSoft to a hybrid cloud setup, using intelligent
routing to gradually shift traffic while monitoring health.

Real-world scenario:
  An enterprise is migrating its Customer API from MuleSoft CloudHub
  to AWS API Gateway. The migration uses a canary deployment strategy:
  1. Deploy the new API on AWS alongside the existing MuleSoft API
  2. Route 10% of traffic to AWS, 90% to MuleSoft
  3. Monitor error rates and latency on both
  4. Gradually increase AWS traffic if healthy
  5. Complete cutover when AWS is proven stable

This pattern is critical for enterprises managing hundreds of APIs
that cannot tolerate downtime during platform migrations.

Author: Venkata Pavan Kumar Gummadi
"""

import asyncio
import random
import time
from typing import Any, Dict, List, Optional

from agentflow.connectors.base import APIEndpoint, APIResponse, BaseConnector
from agentflow.resilience.circuit_breaker import CircuitBreaker
from agentflow.routing.dynamic_router import DynamicRouter, EndpointMetrics, RoutingWeights


# ── Simulated Cloud Connectors ──────────────────────────────────────────


class MuleSoftLegacyConnector(BaseConnector):
    """Simulates the existing MuleSoft CloudHub API (legacy)."""

    def __init__(self, failure_rate: float = 0.02):
        super().__init__(name="MuleSoft-CloudHub-Legacy")
        self.failure_rate = failure_rate
        self.call_count = 0
        self.register_endpoint(APIEndpoint(
            name="Customer API (MuleSoft)",
            method="GET",
            path="/api/v1/customers/{id}",
            description="Legacy customer API on MuleSoft CloudHub",
            tags=["customer", "legacy", "mulesoft"],
            latency_p95_ms=150,
            cost_per_call=0.005,
            rate_limit_rpm=500,
        ))

    def discover(self) -> List[Dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        self.call_count += 1
        latency = random.gauss(120, 30)

        if random.random() < self.failure_rate:
            return APIResponse(
                status_code=503, is_error=True, retryable=True,
                error_message="CloudHub worker temporarily unavailable",
                latency_ms=latency, connector_id=self.connector_id,
            )

        return APIResponse(
            status_code=200,
            body={
                "source": "mulesoft-cloudhub",
                "customer_id": (
                    parameters.get("id", "123") if parameters else "123"
                ),
                "name": "John Smith",
                "tier": "enterprise",
                "response_time_ms": round(latency, 1),
            },
            latency_ms=latency,
            connector_id=self.connector_id,
        )

    async def health_check(self) -> bool:
        return True


class AWSAPIGatewayConnector(BaseConnector):
    """Simulates the new AWS API Gateway (migration target)."""

    def __init__(self, failure_rate: float = 0.05, latency_mean: float = 80):
        super().__init__(name="AWS-API-Gateway-New")
        self.failure_rate = failure_rate
        self.latency_mean = latency_mean
        self.call_count = 0
        self.register_endpoint(APIEndpoint(
            name="Customer API (AWS)",
            method="GET",
            path="/api/v2/customers/{id}",
            description="New customer API on AWS API Gateway + Lambda",
            tags=["customer", "aws", "lambda"],
            latency_p95_ms=100,
            cost_per_call=0.002,
            rate_limit_rpm=1000,
        ))

    def discover(self) -> List[Dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        self.call_count += 1
        latency = random.gauss(self.latency_mean, 20)

        if random.random() < self.failure_rate:
            return APIResponse(
                status_code=500, is_error=True, retryable=True,
                error_message="Lambda cold start timeout",
                latency_ms=latency, connector_id=self.connector_id,
            )

        return APIResponse(
            status_code=200,
            body={
                "source": "aws-api-gateway",
                "customer_id": (
                    parameters.get("id", "123") if parameters else "123"
                ),
                "name": "John Smith",
                "tier": "enterprise",
                "response_time_ms": round(latency, 1),
            },
            latency_ms=latency,
            connector_id=self.connector_id,
        )

    async def health_check(self) -> bool:
        return True


# ── Canary Migration Controller ─────────────────────────────────────────


class CanaryMigrationController:
    """
    Manages gradual traffic shifting between legacy and new APIs.

    Uses AgentFlow's DynamicRouter with custom weights to implement
    a canary deployment strategy. Monitors health metrics at each
    stage and automatically rolls back if the new API degrades.

    Migration stages:
      Stage 0: 100% legacy (baseline)
      Stage 1: 90% legacy / 10% new (canary)
      Stage 2: 70% legacy / 30% new
      Stage 3: 50% legacy / 50% new
      Stage 4: 20% legacy / 80% new
      Stage 5: 0% legacy / 100% new (cutover)
    """

    STAGES = [
        {"name": "Baseline", "legacy_pct": 100, "new_pct": 0},
        {"name": "Canary (10%)", "legacy_pct": 90, "new_pct": 10},
        {"name": "Expand (30%)", "legacy_pct": 70, "new_pct": 30},
        {"name": "Split (50/50)", "legacy_pct": 50, "new_pct": 50},
        {"name": "Shift (80%)", "legacy_pct": 20, "new_pct": 80},
        {"name": "Cutover (100%)", "legacy_pct": 0, "new_pct": 100},
    ]

    def __init__(
        self,
        legacy: MuleSoftLegacyConnector,
        new: AWSAPIGatewayConnector,
        error_threshold: float = 0.10,
        latency_threshold_ms: float = 300,
    ):
        self.legacy = legacy
        self.new = new
        self.error_threshold = error_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.current_stage = 0
        self.router = DynamicRouter(weights=RoutingWeights.balanced())

        # Per-stage metrics
        self.stage_metrics: List[Dict[str, Any]] = []

    async def run_migration(self, requests_per_stage: int = 50):
        """Run the complete canary migration."""
        print(f"\n{'=' * 70}")
        print(f"  CANARY MIGRATION: MuleSoft CloudHub -> AWS API Gateway")
        print(f"  Error threshold: {self.error_threshold:.0%} | "
              f"Latency threshold: {self.latency_threshold_ms}ms")
        print(f"{'=' * 70}")

        for stage_idx, stage in enumerate(self.STAGES):
            self.current_stage = stage_idx
            print(f"\n--- Stage {stage_idx}: {stage['name']} "
                  f"(Legacy: {stage['legacy_pct']}% / New: {stage['new_pct']}%) ---")

            if stage["new_pct"] == 0:
                print("  Establishing baseline metrics on legacy...")
                metrics = await self._run_stage(stage, requests_per_stage, baseline=True)
            else:
                metrics = await self._run_stage(stage, requests_per_stage)

            self.stage_metrics.append(metrics)
            self._print_stage_metrics(metrics)

            # Health gate: check if we should proceed or rollback
            if stage["new_pct"] > 0:
                if not self._health_gate(metrics):
                    print(f"\n  ROLLBACK: New API failed health gate at stage {stage_idx}")
                    print(f"  Rolling back to stage {max(0, stage_idx - 1)}")
                    break
                else:
                    print(f"  HEALTH GATE PASSED — proceeding to next stage")

        self._print_summary()

    async def _run_stage(
        self, stage: Dict, num_requests: int, baseline: bool = False
    ) -> Dict[str, Any]:
        """Run a batch of requests at the current traffic split."""
        legacy_metrics = {"calls": 0, "errors": 0, "latency_sum": 0.0}
        new_metrics = {"calls": 0, "errors": 0, "latency_sum": 0.0}

        for i in range(num_requests):
            # Determine routing based on traffic split
            use_new = (not baseline) and (random.randint(1, 100) <= stage["new_pct"])

            if use_new:
                response = await self.new.invoke("GET /customers/123", parameters={"id": "123"})
                new_metrics["calls"] += 1
                new_metrics["latency_sum"] += response.latency_ms
                if response.is_error:
                    new_metrics["errors"] += 1
                self.router.record_call_result(
                    "aws-endpoint", success=response.success, latency_ms=response.latency_ms
                )
            else:
                response = await self.legacy.invoke("GET /customers/123", parameters={"id": "123"})
                legacy_metrics["calls"] += 1
                legacy_metrics["latency_sum"] += response.latency_ms
                if response.is_error:
                    legacy_metrics["errors"] += 1
                self.router.record_call_result(
                    "mulesoft-endpoint", success=response.success, latency_ms=response.latency_ms
                )

        legacy_calls = legacy_metrics["calls"]
        new_calls = new_metrics["calls"]
        return {
            "stage": stage["name"],
            "total_requests": num_requests,
            "legacy": {
                "calls": legacy_calls,
                "errors": legacy_metrics["errors"],
                "error_rate": (
                    legacy_metrics["errors"] / max(legacy_calls, 1)
                ),
                "avg_latency_ms": round(
                    legacy_metrics["latency_sum"] / max(legacy_calls, 1), 1
                ),
            },
            "new": {
                "calls": new_calls,
                "errors": new_metrics["errors"],
                "error_rate": (
                    new_metrics["errors"] / max(new_calls, 1)
                ),
                "avg_latency_ms": round(
                    new_metrics["latency_sum"] / max(new_calls, 1), 1
                ),
            },
        }

    def _health_gate(self, metrics: dict) -> bool:
        """Check if the new API passes the health gate for promotion."""
        new = metrics["new"]
        if new["calls"] == 0:
            return True
        error_rate = new['error_rate']
        if error_rate > self.error_threshold:
            print(
                f"  FAILED: Error rate {error_rate:.1%} > "
                f"threshold {self.error_threshold:.0%}"
            )
            return False
        latency = new["avg_latency_ms"]
        if latency > self.latency_threshold_ms:
            print(
                f"  FAILED: Latency {latency}ms > "
                f"threshold {self.latency_threshold_ms}ms"
            )
            return False
        return True

    def _print_stage_metrics(self, metrics: Dict):
        legacy = metrics["legacy"]
        new = metrics["new"]

        if legacy["calls"] > 0:
            print(f"  Legacy:  {legacy['calls']} calls | "
                  f"errors: {legacy['errors']} ({legacy['error_rate']:.1%}) | "
                  f"avg latency: {legacy['avg_latency_ms']}ms")
        if new["calls"] > 0:
            print(f"  New:     {new['calls']} calls | "
                  f"errors: {new['errors']} ({new['error_rate']:.1%}) | "
                  f"avg latency: {new['avg_latency_ms']}ms")

    def _print_summary(self):
        print(f"\n{'=' * 70}")
        print(f"  MIGRATION SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Stages completed: {len(self.stage_metrics)}/{len(self.STAGES)}")
        print(f"  Legacy total calls: {self.legacy.call_count}")
        print(f"  New total calls: {self.new.call_count}")

        final = self.stage_metrics[-1] if self.stage_metrics else {}
        if final.get("new", {}).get("calls", 0) > 0:
            final_stage = final["stage"]
            if "Cutover" in final_stage:
                print(f"  Result: MIGRATION COMPLETE")
            else:
                print(f"  Result: Stable at '{final_stage}'")
        print(f"{'=' * 70}")


# ── Main ────────────────────────────────────────────────────────────────


async def main():
    print("=" * 70)
    print("  MULTI-CLOUD API MIGRATION — Canary Deployment Strategy")
    print("=" * 70)

    # Scenario 1: Successful migration (low failure rate on new API)
    print("\n[Scenario 1] Successful Migration (AWS stable)")
    legacy = MuleSoftLegacyConnector(failure_rate=0.02)
    new_api = AWSAPIGatewayConnector(failure_rate=0.03, latency_mean=80)
    controller = CanaryMigrationController(legacy, new_api)
    await controller.run_migration(requests_per_stage=30)

    # Scenario 2: Rollback (high failure rate on new API)
    print(f"\n\n{'#' * 70}")
    print("\n[Scenario 2] Rollback Scenario (AWS unstable)")
    legacy2 = MuleSoftLegacyConnector(failure_rate=0.02)
    unstable_api = AWSAPIGatewayConnector(failure_rate=0.20, latency_mean=250)
    controller2 = CanaryMigrationController(legacy2, unstable_api, error_threshold=0.10)
    await controller2.run_migration(requests_per_stage=30)


if __name__ == "__main__":
    asyncio.run(main())
