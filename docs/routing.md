# AgentFlow Routing Strategies

**Author:** Venkata Pavan Kumar Gummadi

## Table of Contents

1. [Overview](#overview)
2. [Multi-Dimensional Scoring](#multi-dimensional-scoring)
3. [RoutingWeights Presets](#routingweights-presets)
4. [Scoring Algorithm](#scoring-algorithm)
5. [Capability Matching](#capability-matching)
6. [Health-Aware Routing](#health-aware-routing)
7. [Custom Routing Strategies](#custom-routing-strategies)
8. [Configuration Examples](#configuration-examples)
9. [Performance Considerations](#performance-considerations)

---

## Overview

Intelligent API routing is critical in multi-agent orchestration systems where requests must be distributed across heterogeneous endpoints with varying performance characteristics, costs, and availability states. The **DynamicRouter** is AgentFlow's core routing engine, designed to make real-time routing decisions based on a multi-dimensional evaluation framework.

### Why Intelligent API Routing Matters

In production multi-agent systems, not all API endpoints are equal:
- **Latency**: Some endpoints are geographically closer or more optimized
- **Cost**: Different providers charge different rates; some are free tier, others premium
- **Rate Limits**: Endpoints have different throughput capacities
- **Capability**: Not all endpoints support the same set of operations
- **Health**: Endpoints may temporarily degrade or become unavailable

Without intelligent routing, you risk:
- Poor user experience due to slow responses
- Unnecessary cost overruns
- Rate limit collisions and backpressure
- Capability mismatches (sending requests to endpoints that can't handle them)
- Cascading failures when unhealthy endpoints aren't avoided

### The DynamicRouter Concept

The DynamicRouter evaluates each candidate endpoint across five dimensions, combines these scores using configurable weights, and selects the highest-scoring endpoint. This enables nuanced control over routing priorities—whether you want blazing-fast responses, minimal costs, maximum reliability, or a balanced mix.

---

## Multi-Dimensional Scoring

The DynamicRouter evaluates each dimension on a normalized scale of [0, 1], where 1 is the best outcome.

### The Five Dimensions

#### 1. Latency Weight (`latency_weight`)
- **Measures**: Average response time of the endpoint
- **Normalization**: Inverted—endpoints with lower latency score higher
  ```
  latency_score = 1 / (1 + normalized_latency)
  ```
- **Use Case**: Prioritize when user-facing latency is critical
- **Source**: Aggregated from recent request timings and SLA metrics

#### 2. Cost Weight (`cost_weight`)
- **Measures**: Estimated cost per request (in currency units or points)
- **Normalization**: Inverted—cheaper endpoints score higher
  ```
  cost_score = 1 / (1 + normalized_cost)
  ```
- **Use Case**: Minimize infrastructure spending, especially for high-volume workloads
- **Source**: Published pricing from API providers or internal cost tracking

#### 3. Rate Limit Weight (`rate_limit_weight`)
- **Measures**: Available capacity relative to limit
  ```
  rate_limit_score = available_capacity / total_capacity
  ```
- **Normalization**: Range [0, 1] where 1 = no rate limiting pressure
- **Use Case**: Avoid overloading constrained endpoints
- **Source**: Real-time monitoring of rate limit usage and headers (e.g., X-RateLimit-Remaining)

#### 4. Capability Weight (`capability_weight`)
- **Measures**: Semantic match between request intent and endpoint capabilities
- **Normalization**: Tag-based matching score, range [0, 1]
  ```
  capability_score = matched_tags / total_required_tags
  ```
- **Use Case**: Ensure routed endpoint can actually handle the request
- **Source**: Endpoint capability declarations (tags/features list)

#### 5. Health Weight (`health_weight`)
- **Measures**: Circuit breaker state and recent error rates
- **Normalization**: 
  - Healthy (green) = 1.0
  - Degraded (yellow) = 0.5
  - Unhealthy (red) = 0.0
- **Use Case**: Automatically avoid or reduce traffic to failing endpoints
- **Source**: Internal circuit breaker tracking and error rate monitoring

### Composite Score Calculation

Each dimension is multiplied by its configured weight and summed:

```
composite_score = (
    latency_score * weights.latency +
    cost_score * weights.cost +
    rate_limit_score * weights.rate_limit +
    capability_score * weights.capability +
    health_score * weights.health
) / sum(weights)
```

The weights are normalized (sum to 1.0) to ensure the composite score remains in [0, 1].

---

## RoutingWeights Presets

AgentFlow provides four built-in presets optimized for common scenarios:

| Preset | Latency | Cost | Rate Limit | Capability | Health | Best For |
|--------|---------|------|-----------|------------|--------|----------|
| **balanced()** | 0.2 | 0.2 | 0.2 | 0.2 | 0.2 | General-purpose, no strong preference |
| **low_latency()** | 0.5 | 0.1 | 0.1 | 0.1 | 0.2 | User-facing APIs, real-time interactions |
| **cost_optimized()** | 0.1 | 0.5 | 0.1 | 0.1 | 0.2 | Batch processing, cost-sensitive workloads |
| **high_availability()** | 0.1 | 0.1 | 0.2 | 0.2 | 0.4 | Mission-critical systems, SLA-driven |

### Preset Definitions

```python
class RoutingWeights:
    latency: float
    cost: float
    rate_limit: float
    capability: float
    health: float
    
    @staticmethod
    def balanced() -> 'RoutingWeights':
        """Equal weight to all dimensions."""
        return RoutingWeights(
            latency=0.2, cost=0.2, rate_limit=0.2,
            capability=0.2, health=0.2
        )
    
    @staticmethod
    def low_latency() -> 'RoutingWeights':
        """Heavily prioritize response speed."""
        return RoutingWeights(
            latency=0.5, cost=0.1, rate_limit=0.1,
            capability=0.1, health=0.2
        )
    
    @staticmethod
    def cost_optimized() -> 'RoutingWeights':
        """Minimize per-request cost."""
        return RoutingWeights(
            latency=0.1, cost=0.5, rate_limit=0.1,
            capability=0.1, health=0.2
        )
    
    @staticmethod
    def high_availability() -> 'RoutingWeights':
        """Maximize reliability and redundancy."""
        return RoutingWeights(
            latency=0.1, cost=0.1, rate_limit=0.2,
            capability=0.2, health=0.4
        )
```

---

## Scoring Algorithm

The DynamicRouter uses a deterministic, step-by-step scoring process:

### Step 1: Filter by Capability
Exclude endpoints that cannot satisfy the request's capability requirements.

```python
candidates = [
    ep for ep in endpoints
    if ep.supports_capability(request.intent)
]

if not candidates:
    raise RoutingError("No endpoints support required capability")
```

### Step 2: Normalize Each Dimension

For each candidate endpoint, compute normalized scores:

```python
def normalize_dimension(endpoints, dimension):
    """
    Normalize dimension values to [0, 1] range.
    Invert for 'lower is better' dimensions.
    """
    values = [getattr(ep, dimension) for ep in endpoints]
    min_val = min(values)
    max_val = max(values)
    
    normalized = {}
    for ep in endpoints:
        val = getattr(ep, dimension)
        if dimension in ['latency', 'cost']:
            # Lower is better: invert
            score = (max_val - val) / (max_val - min_val) if max_val > min_val else 1.0
        else:
            # Higher is better
            score = (val - min_val) / (max_val - min_val) if max_val > min_val else 1.0
        normalized[ep.id] = score
    
    return normalized
```

### Step 3: Apply Weights and Compute Composite Score

```python
def compute_composite_score(endpoint, dimensions, weights):
    """
    Combine normalized dimension scores using weights.
    """
    weighted_sum = (
        dimensions['latency'][endpoint.id] * weights.latency +
        dimensions['cost'][endpoint.id] * weights.cost +
        dimensions['rate_limit'][endpoint.id] * weights.rate_limit +
        dimensions['capability'][endpoint.id] * weights.capability +
        dimensions['health'][endpoint.id] * weights.health
    )
    
    # Normalize by sum of weights
    total_weight = (
        weights.latency + weights.cost + weights.rate_limit +
        weights.capability + weights.health
    )
    
    return weighted_sum / total_weight
```

### Step 4: Select Highest-Scoring Endpoint

```python
def select_endpoint(candidates, dimensions, weights):
    """
    Score all candidates and return the highest.
    """
    scores = {
        ep.id: compute_composite_score(ep, dimensions, weights)
        for ep in candidates
    }
    
    best_id = max(scores, key=scores.get)
    return next(ep for ep in candidates if ep.id == best_id), scores
```

---

## Capability Matching

Capability matching ensures requests are only routed to endpoints that can handle them. This prevents 404s, 501s, or unexpected failures.

### Tag-Based Semantic Matching

Endpoints declare their capabilities as **tags**:

```python
class APIEndpoint:
    id: str
    tags: Set[str]  # e.g., {'llm', 'gpt-4', 'embeddings', 'vision'}
    # ...

# Examples:
endpoint_1 = APIEndpoint(
    id='openai-api',
    tags={'llm', 'gpt-4', 'gpt-3.5', 'embeddings', 'vision'}
)

endpoint_2 = APIEndpoint(
    id='anthropic-api',
    tags={'llm', 'claude', 'embeddings'}
)

endpoint_3 = APIEndpoint(
    id='local-embeddings',
    tags={'embeddings'}
)
```

Requests specify required capabilities as **intent keywords**:

```python
class RoutingRequest:
    intent: str  # "I need LLM with vision support"
    required_tags: Set[str]  # extracted from intent, e.g., {'llm', 'vision'}
    # ...
```

### Matching Logic

```python
def matches_capability(endpoint, request):
    """
    Check if endpoint covers required capabilities.
    A match occurs when endpoint tags include all required tags.
    """
    return request.required_tags.issubset(endpoint.tags)

def capability_score(endpoint, request):
    """
    Score based on how many requested tags are matched.
    Penalties for extra unneeded tags.
    """
    matched = len(request.required_tags & endpoint.tags)
    extra = len(endpoint.tags - request.required_tags)
    
    match_ratio = matched / len(request.required_tags) if request.required_tags else 1.0
    efficiency = 1.0 / (1.0 + 0.1 * extra)  # Small penalty for bloat
    
    return match_ratio * efficiency
```

---

## Health-Aware Routing

The circuit breaker pattern prevents cascading failures by automatically shedding traffic from unhealthy endpoints.

### Circuit Breaker States

```python
class CircuitBreakerState(Enum):
    HEALTHY = 1.0       # Green: accepting full traffic
    DEGRADED = 0.5      # Yellow: accepting reduced traffic
    UNHEALTHY = 0.0     # Red: circuit open, no traffic
```

### State Transitions

```python
class CircuitBreaker:
    state: CircuitBreakerState
    failure_count: int
    success_count: int
    last_failure_time: datetime
    
    # Thresholds
    FAILURE_THRESHOLD = 5
    SUCCESS_THRESHOLD = 10
    TIMEOUT_MINUTES = 5
    
    def record_success(self):
        self.failure_count = 0
        self.success_count += 1
        if self.success_count >= self.SUCCESS_THRESHOLD:
            if self.state == CircuitBreakerState.DEGRADED:
                self.state = CircuitBreakerState.HEALTHY
                self.success_count = 0
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.FAILURE_THRESHOLD:
            self.state = CircuitBreakerState.UNHEALTHY
    
    def check_timeout(self):
        """Allow gradual recovery after timeout."""
        if self.state == CircuitBreakerState.UNHEALTHY:
            elapsed = (datetime.now() - self.last_failure_time).total_seconds() / 60
            if elapsed > self.TIMEOUT_MINUTES:
                self.state = CircuitBreakerState.DEGRADED
                self.failure_count = 0
```

### Impact on Routing

Health state directly feeds into the `health_weight` dimension:

```python
def health_score(endpoint):
    """Convert circuit breaker state to [0, 1] score."""
    cb_state = endpoint.circuit_breaker.state
    if cb_state == CircuitBreakerState.HEALTHY:
        return 1.0
    elif cb_state == CircuitBreakerState.DEGRADED:
        return 0.5
    else:  # UNHEALTHY
        return 0.0
```

Endpoints with `health_score = 0.0` can still be routed to (if no other options exist), but will lose all points from the health dimension, making them least preferred.

---

## Custom Routing Strategies

Users can create custom routing strategies by defining custom `RoutingWeights`:

### Example: ML Inference Priority

Prioritize quality over cost for ML inference:

```python
ml_inference_weights = RoutingWeights(
    latency=0.15,
    cost=0.1,
    rate_limit=0.15,
    capability=0.35,  # Ensure correct model/framework
    health=0.25       # Avoid unstable inference servers
)

router = DynamicRouter(weights=ml_inference_weights)
```

### Example: Batch Processing

Maximize cost savings for non-urgent workloads:

```python
batch_processing_weights = RoutingWeights(
    latency=0.05,
    cost=0.6,         # Minimize spend
    rate_limit=0.05,
    capability=0.15,
    health=0.15       # Basic reliability
)

router = DynamicRouter(weights=batch_processing_weights)
```

### Extending the Router

Create a custom router subclass for specialized logic:

```python
class SeasonalRouter(DynamicRouter):
    """Router that adjusts weights based on time of day."""
    
    def get_weights(self, request):
        """Override to return time-aware weights."""
        from datetime import datetime
        hour = datetime.now().hour
        
        if 8 <= hour < 18:  # Business hours: prioritize speed
            return RoutingWeights.low_latency()
        else:  # Off-hours: optimize cost
            return RoutingWeights.cost_optimized()
    
    def route(self, request, endpoints):
        """Use time-aware weights."""
        weights = self.get_weights(request)
        return super().route(request, endpoints, weights)
```

---

## Configuration Examples

### Example 1: Basic Setup with Balanced Routing

```python
from agentflow.routing import DynamicRouter, RoutingWeights

# Initialize router with balanced preset
router = DynamicRouter(weights=RoutingWeights.balanced())

# Register endpoints
endpoints = [
    APIEndpoint(
        id='api-1',
        latency_ms=50,
        cost_per_request=0.01,
        tags={'llm', 'fast'},
        rate_limit_remaining=9500
    ),
    APIEndpoint(
        id='api-2',
        latency_ms=100,
        cost_per_request=0.005,
        tags={'llm', 'cheap'},
        rate_limit_remaining=5000
    ),
]

# Route a request
request = RoutingRequest(
    intent="Generate summary",
    required_tags={'llm'}
)

selected_endpoint, scores = router.route(request, endpoints)
print(f"Selected: {selected_endpoint.id}")
print(f"Scores: {scores}")
# Output:
# Selected: api-1
# Scores: {'api-1': 0.68, 'api-2': 0.52}
```

### Example 2: High-Availability Setup

```python
# Production setup prioritizing reliability
router = DynamicRouter(weights=RoutingWeights.high_availability())

endpoints = [
    APIEndpoint(
        id='primary-us-east',
        latency_ms=25,
        cost_per_request=0.02,
        tags={'llm', 'embeddings', 'gpt-4'},
        rate_limit_remaining=8000,
        health_state=CircuitBreakerState.HEALTHY
    ),
    APIEndpoint(
        id='secondary-us-west',
        latency_ms=80,
        cost_per_request=0.02,
        tags={'llm', 'embeddings', 'gpt-4'},
        rate_limit_remaining=9500,
        health_state=CircuitBreakerState.HEALTHY
    ),
    APIEndpoint(
        id='backup-eu',
        latency_ms=150,
        cost_per_request=0.025,
        tags={'llm', 'embeddings'},
        rate_limit_remaining=5000,
        health_state=CircuitBreakerState.DEGRADED
    ),
]

request = RoutingRequest(
    intent="Mission-critical LLM query",
    required_tags={'llm', 'embeddings', 'gpt-4'}
)

endpoint, _ = router.route(request, endpoints)
# Likely selects 'primary-us-east' or 'secondary-us-west'
# Avoids 'backup-eu' due to degraded health despite matching tags
```

### Example 3: Cost-Optimized Batch Processing

```python
router = DynamicRouter(weights=RoutingWeights.cost_optimized())

endpoints = [
    APIEndpoint(
        id='expensive-fast',
        latency_ms=10,
        cost_per_request=0.50,
        tags={'llm'},
        rate_limit_remaining=1000
    ),
    APIEndpoint(
        id='cheap-slow',
        latency_ms=500,
        cost_per_request=0.01,
        tags={'llm'},
        rate_limit_remaining=50000
    ),
]

request = RoutingRequest(
    intent="Process 10k documents with LLM",
    required_tags={'llm'}
)

endpoint, _ = router.route(request, endpoints)
# Selects 'cheap-slow' despite higher latency
# Cost savings: $0.01 * 10k = $100 vs $0.50 * 10k = $5000
```

---

## Performance Considerations

### 1. Score Caching

Recalculating scores on every request is expensive. Cache scores with appropriate TTL:

```python
class CachedDynamicRouter(DynamicRouter):
    def __init__(self, weights, cache_ttl_seconds=30):
        super().__init__(weights)
        self.cache_ttl = cache_ttl_seconds
        self.score_cache = {}
        self.cache_timestamps = {}
    
    def route(self, request, endpoints):
        cache_key = self._make_cache_key(request, endpoints)
        
        # Check cache validity
        if cache_key in self.score_cache:
            age = time.time() - self.cache_timestamps[cache_key]
            if age < self.cache_ttl:
                return self.score_cache[cache_key]
        
        # Recompute if cache miss or expired
        result = super().route(request, endpoints)
        self.score_cache[cache_key] = result
        self.cache_timestamps[cache_key] = time.time()
        
        return result
    
    def _make_cache_key(self, request, endpoints):
        ep_ids = tuple(sorted(ep.id for ep in endpoints))
        return (request.intent, ep_ids)
```

### 2. Re-evaluation Frequency

Adjust re-evaluation based on endpoint volatility:

```python
class AdaptiveRouter(DynamicRouter):
    """Adjusts cache TTL based on endpoint health changes."""
    
    def __init__(self, weights):
        super().__init__(weights)
        self.health_cache = {}
    
    def get_cache_ttl(self, endpoints):
        """Shorter TTL if health states are unstable."""
        health_changes = sum(
            1 for ep in endpoints
            if ep.health_state != self.health_cache.get(ep.id)
        )
        
        # Update cache
        self.health_cache = {ep.id: ep.health_state for ep in endpoints}
        
        # More frequent re-evaluation if instability detected
        if health_changes > 0:
            return 5  # 5 second TTL during instability
        else:
            return 60  # 60 second TTL during stability
```

### 3. Batch Routing

For high-throughput scenarios, batch multiple requests to amortize normalization costs:

```python
def route_batch(requests, endpoints, weights, batch_size=100):
    """Route multiple requests efficiently."""
    results = []
    
    # Normalize dimensions once for all requests
    dimensions = {
        'latency': normalize_dimension(endpoints, 'latency_ms'),
        'cost': normalize_dimension(endpoints, 'cost_per_request'),
        'rate_limit': normalize_dimension(endpoints, 'rate_limit_remaining'),
        'capability': {ep.id: capability_score(ep, req) for ep in endpoints for req in [requests[0]]},
        'health': normalize_dimension(endpoints, 'health_state'),
    }
    
    for request in requests:
        candidates = filter_by_capability(endpoints, request)
        scores = compute_scores(candidates, dimensions, weights)
        selected = max(candidates, key=lambda ep: scores[ep.id])
        results.append((request, selected, scores))
    
    return results
```

### 4. Latency Budgets

Ensure routing overhead stays within acceptable bounds:

```python
import time

def route_with_budget(request, endpoints, weights, max_routing_time_ms=10):
    """Ensure routing completes within latency budget."""
    start = time.time()
    
    try:
        result = super().route(request, endpoints, weights)
        elapsed = (time.time() - start) * 1000
        
        if elapsed > max_routing_time_ms:
            logger.warn(f"Routing exceeded budget: {elapsed:.2f}ms > {max_routing_time_ms}ms")
        
        return result
    except TimeoutError:
        # Fallback to simple random selection if routing times out
        return random.choice(endpoints)
```

---

## Summary

AgentFlow's intelligent routing engine balances multiple competing objectives to deliver optimal performance across diverse workloads. By understanding the five dimensions, presets, and customization options, you can tune routing behavior for your specific use case—whether that's blazing speed, minimal cost, maximum reliability, or a carefully calibrated mix.

Start with the presets, monitor routing decisions, and adapt custom weights as your system evolves.
