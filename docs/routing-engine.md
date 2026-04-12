# Multi-Dimensional Routing Engine

## Overview

AgentFlow's routing engine scores API endpoints in real time across five dimensions to select the optimal endpoint for each request. The `AdaptiveWeightOptimizer` extends the `DynamicRouter` with self-tuning weights that evolve based on observed performance.

## Architecture

```
                    ┌─────────────────────────┐
                    │   Incoming API Request   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Intent Parser (NLP)    │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Capability Matcher     │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
     ┌────────▼───────┐ ┌───────▼────────┐ ┌───────▼────────┐
     │  Endpoint A     │ │  Endpoint B     │ │  Endpoint C     │
     │  Score: 0.87    │ │  Score: 0.92    │ │  Score: 0.71    │
     └────────┬───────┘ └───────┬────────┘ └───────┬────────┘
              │                  │                   │
              └──────────┬───────┘───────────────────┘
                         │
                    ┌────▼──────────────────┐
                    │ Select Highest → B     │
                    └────┬──────────────────┘
                         │
                    ┌────▼──────────────────┐
                    │ Execute & Feed Back    │
                    │ to Weight Optimizer    │
                    └───────────────────────┘
```

## Composite Scoring Function

```
S(endpoint) = w₁·latency + w₂·cost + w₃·headroom + w₄·capability + w₅·health
```

All scores normalized to [0.0, 1.0]. Weights are dynamically adjusted by `AdaptiveWeightOptimizer`.

### Dimensions

| Dimension | Measures | Normalization |
|-----------|----------|---------------|
| Latency | Response time (ms) | `1 - (latency / max_observed)` |
| Cost | Per-call cost ($) | `1 - (cost / max_in_pool)` |
| Rate Limit Headroom | Remaining quota % | Direct (0.0–1.0) |
| Capability Match | Feature coverage | Jaccard similarity |
| Health Status | Endpoint health | Rolling success rate |

## Adaptive Weight Optimization

The `AdaptiveWeightOptimizer` adjusts weights when SLA violations are detected:

1. **Observe** — collect performance snapshots after each API call
2. **Smooth** — apply EMA to reduce noise
3. **Detect** — compare against SLA thresholds
4. **Adjust** — increase violated dimension weights with momentum
5. **Normalize** — clamp within [0.05, 0.50], normalize to sum = 1.0

### Usage

```python
from agentflow.routing import AdaptiveWeightOptimizer, RoutingDimension, DimensionSLA

optimizer = AdaptiveWeightOptimizer(
    sla_config={
        RoutingDimension.LATENCY: DimensionSLA(RoutingDimension.LATENCY, target=100.0),
        RoutingDimension.HEALTH_STATUS: DimensionSLA(RoutingDimension.HEALTH_STATUS, target=0.99),
    },
    ema_decay=0.95,
    learning_rate=0.05,
)
```

## References

- AgentFlow Paper, Section 3.2: Multi-Dimensional Routing Engine
- AgentFlow Paper, Equation 1: Composite Routing Score
