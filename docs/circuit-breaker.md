# Adaptive Circuit Breaker with Exponential Cooldown Learning

## Overview

AgentFlow's `ExponentialCooldownStrategy` extends the `CircuitBreaker` with learning-based cooldown timing. Instead of fixed recovery timeouts, each endpoint independently learns its optimal recovery timing.

## State Machine

```
         success
    ┌──────────────────────────────────────┐
    │                                      │
    ▼       failures >= threshold           │
 CLOSED ────────────────────────────► OPEN
    ▲                                  │ ▲
    │            cooldown elapsed      │ │
    │         ┌────────────────────────┘ │
    │         ▼        probe fails       │
    │     HALF_OPEN ─────────────────────┘
    │         │
    │         │ probe succeeds
    └─────────┘
```

## Cooldown Algorithm

```
cooldown(n) = min(base × decay_factor^n × (1 ± jitter), max_cooldown)
```

### Learning Rules

| Recovery Outcome | Decay Adjustment | Effect |
|-----------------|------------------|--------|
| Success | `×(1 - 0.1)` → decreases | Shorter future cooldowns |
| Failure | `×(1 + 0.2)` → increases | Longer future cooldowns |

Bounds: decay_factor ∈ [1.5, 10.0]

## Usage

```python
from agentflow.resilience.cooldown_strategy import ExponentialCooldownStrategy

strategy = ExponentialCooldownStrategy(
    base_cooldown_ms=1000,
    max_cooldown_ms=300_000,
    failure_threshold=3,
)

# Record failure
cooldown = strategy.record_failure("payments-api")

# Check if ready to probe
if strategy.should_attempt_recovery("payments-api"):
    try:
        result = call_api()
        strategy.record_recovery_success("payments-api")
    except Exception:
        strategy.record_recovery_failure("payments-api")
```

## References

- AgentFlow Paper, Section 4.2: Adaptive Circuit Breaker
- AgentFlow Paper, Equation 2: Cooldown Duration Function
