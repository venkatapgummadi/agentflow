"""
Example: Resilience Patterns with AgentFlow.

Demonstrates circuit breaker, adaptive retry, and intelligent routing
for building fault-tolerant API orchestrations.

Author: Venkata Pavan Kumar Gummadi
"""

from agentflow.resilience.circuit_breaker import CircuitBreaker
from agentflow.resilience.retry_policy import (
    BackoffStrategy,
    ErrorClass,
    RetryPolicy,
)
from agentflow.routing.dynamic_router import (
    DynamicRouter,
    RoutingWeights,
)


def demo_circuit_breaker():
    """Demonstrate adaptive circuit breaker behavior."""
    print("=== Circuit Breaker Demo ===\n")

    cb = CircuitBreaker(
        name="payment-service",
        failure_threshold=3,
        success_threshold=2,
        cooldown_seconds=5.0,
    )

    # Normal operation
    print(f"State: {cb.state.value}")
    cb.record_success()
    cb.record_success()
    print(f"After 2 successes: {cb.state.value}")

    # Simulate failures
    for i in range(3):
        cb.record_failure()
        print(f"After failure {i + 1}: {cb.state.value}")

    print(f"Allow request? {cb.allow_request()}")
    print(f"Metrics: {cb.get_metrics()}")


def demo_retry_strategies():
    """Demonstrate different retry backoff strategies."""
    print("\n=== Retry Strategy Comparison ===\n")

    strategies = [
        ("Exponential", BackoffStrategy.EXPONENTIAL),
        ("Linear", BackoffStrategy.LINEAR),
        ("Fibonacci", BackoffStrategy.FIBONACCI),
        ("Adaptive (rate-limited)", BackoffStrategy.ADAPTIVE),
    ]

    for name, strategy in strategies:
        policy = RetryPolicy(strategy=strategy, jitter=False)
        waits = [
            round(
                policy.calculate_backoff(
                    attempt=i,
                    config={"backoff_base": 1.0, "backoff_max": 60.0},
                    error_class=ErrorClass.RATE_LIMITED,
                ),
                2,
            )
            for i in range(5)
        ]
        print(f"{name:25s}: {waits}")


def demo_intelligent_routing():
    """Demonstrate dynamic routing across multiple endpoints."""
    print("\n=== Intelligent Routing Demo ===\n")

    candidates = [
        {
            "endpoint_id": "us-east-primary",
            "latency_p95_ms": 45,
            "cost_per_call": 0.001,
            "rate_limit_rpm": 1000,
            "tags": ["customer", "crm"],
        },
        {
            "endpoint_id": "eu-west-replica",
            "latency_p95_ms": 120,
            "cost_per_call": 0.0005,
            "rate_limit_rpm": 500,
            "tags": ["customer", "crm"],
        },
        {
            "endpoint_id": "us-west-budget",
            "latency_p95_ms": 200,
            "cost_per_call": 0.0001,
            "rate_limit_rpm": 2000,
            "tags": ["customer"],
        },
    ]

    # Low latency routing
    router = DynamicRouter(weights=RoutingWeights.low_latency())
    result = router.route(candidates, required_capability="customer.crm")
    print(f"Low Latency picks: {result['endpoint_id']}")

    scores = router.score_all(candidates, required_capability="customer.crm")
    for s in sorted(scores, key=lambda x: x.total_score, reverse=True):
        print(f"  {s.endpoint_id}: {s.total_score:.4f}")

    # Low cost routing
    router = DynamicRouter(weights=RoutingWeights.low_cost())
    result = router.route(candidates, required_capability="customer")
    print(f"\nLow Cost picks: {result['endpoint_id']}")

    # High availability routing
    router = DynamicRouter(weights=RoutingWeights.high_availability())
    result = router.route(candidates)
    print(f"High Availability picks: {result['endpoint_id']}")


if __name__ == "__main__":
    demo_circuit_breaker()
    demo_retry_strategies()
    demo_intelligent_routing()
