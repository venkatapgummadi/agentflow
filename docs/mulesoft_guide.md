# AgentFlow MuleSoft Integration Guide

**Author:** Venkata Pavan Kumar Gummadi  
**Version:** 1.0  
**Last Updated:** April 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Configuration](#configuration)
3. [API Discovery](#api-discovery)
4. [Runtime Orchestration](#runtime-orchestration)
5. [Authentication](#authentication)
6. [Advanced Patterns](#advanced-patterns)
7. [Complete Example](#complete-example)

---

## Overview

### Why MuleSoft Integration Matters

MuleSoft's Anypoint Platform is a leading enterprise integration platform that enables organizations to connect APIs, applications, and data at scale. AgentFlow's native MuleSoft support bridges the gap between AI-powered orchestration and enterprise integration patterns, allowing intelligent agents to discover, invoke, and compose MuleSoft-managed APIs with minimal configuration overhead.

This integration is critical for organizations that:

- Maintain complex API ecosystems across multiple cloud and on-premises systems
- Require centralized API governance and lifecycle management
- Need AI agents to dynamically discover and orchestrate APIs in real-time
- Operate in regulated industries with strict compliance and auditing requirements
- Deploy APIs across development, staging, and production environments

### Anypoint Platform Concepts

**Anypoint Platform** is MuleSoft's unified integration platform comprising:

- **Anypoint Exchange:** A central repository for API specifications, connectors, and templates
- **API Manager:** Centralized API lifecycle management, versicing, and policy enforcement
- **Runtime Manager:** Orchestration and monitoring of Mule runtime instances across CloudHub and on-premises
- **Access Management:** OAuth2-based authentication and organization/environment isolation
- **Analytics:** Real-time integration metrics, logs, and diagnostics

AgentFlow integrates with these components to provide:

- **Auto-discovery** of APIs registered in Anypoint Exchange
- **Dynamic routing** to CloudHub or on-premises Mule runtimes
- **Policy-aware execution** respecting rate limiting, throttling, and security policies
- **Multi-environment orchestration** for API promotion across deployment stages
- **Intelligent caching** for API specifications and authentication tokens

---

## Configuration

### MuleSoftConnector Setup

The `MuleSoftConnector` is the primary interface for configuring AgentFlow's MuleSoft integration.

#### Basic Configuration

```python
from agentflow.connectors.mulesoft import MuleSoftConnector, MuleSoftConfig

# Initialize with Anypoint Platform credentials
config = MuleSoftConfig(
    anypoint_url="https://anypoint.mulesoft.com",
    org_id="your-org-uuid",
    environment="production",
    client_id="your-client-id",
    client_secret="your-client-secret"  # Store securely in environment variables
)

connector = MuleSoftConnector(config=config)
```

#### Configuration Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `anypoint_url` | str | Yes | Base URL for Anypoint Platform (typically `https://anypoint.mulesoft.com`) |
| `org_id` | str | Yes | Organization UUID from Anypoint Platform |
| `environment` | str | Yes | Target environment: `development`, `staging`, or `production` |
| `client_id` | str | Yes | OAuth2 client ID for service account authentication |
| `client_secret` | str | Yes | OAuth2 client secret (store in env vars or secrets manager) |
| `token_cache_ttl` | int | No | Token cache time-to-live in seconds (default: 3600) |
| `api_discovery_interval` | int | No | Interval for refreshing API cache in seconds (default: 1800) |
| `cloudHub_aware` | bool | No | Enable CloudHub-specific optimizations (default: True) |
| `disable_ssl_verification` | bool | No | Disable SSL verification (dev only, default: False) |

#### Environment-Specific Configuration

```python
import os
from agentflow.connectors.mulesoft import MuleSoftConnector, MuleSoftConfig

# Load from environment variables for secure deployment
config = MuleSoftConfig(
    anypoint_url=os.getenv("MULESOFT_ANYPOINT_URL"),
    org_id=os.getenv("MULESOFT_ORG_ID"),
    environment=os.getenv("MULESOFT_ENV"),  # Set per deployment
    client_id=os.getenv("MULESOFT_CLIENT_ID"),
    client_secret=os.getenv("MULESOFT_CLIENT_SECRET"),
    api_discovery_interval=int(os.getenv("API_DISCOVERY_INTERVAL", "1800")),
    token_cache_ttl=int(os.getenv("TOKEN_CACHE_TTL", "3600"))
)

connector = MuleSoftConnector(config=config)
```

---

## API Discovery

### Automatic API Discovery

AgentFlow automatically discovers APIs registered in Anypoint Exchange and caches their specifications. The discovery process runs:

1. **On connector initialization** — Initial population of API registry
2. **On a scheduled interval** — Periodic refresh (configurable via `api_discovery_interval`)
3. **On-demand** — Via explicit `refresh_api_catalog()` call

### Discovery Flow

```python
# Automatic discovery happens during connector initialization
connector = MuleSoftConnector(config=config)

# The connector performs the following internally:
# 1. Authenticates with Anypoint Platform
# 2. Queries Anypoint Exchange for APIs in the organization
# 3. Downloads RAML/OAS specifications for each API
# 4. Parses endpoint definitions and operation metadata
# 5. Caches specifications for the configured environment
# 6. Registers endpoints with AgentFlow's Dynamic Router
```

### RAML and OpenAPI Specification Parsing

AgentFlow's discovery mechanism supports both **RAML 1.0** and **OpenAPI 3.0** specifications:

#### Supported Specification Features

- **Endpoints:** Full URI path and HTTP method definitions
- **Parameters:** Query, path, header, and request body parameters with validation rules
- **Request/Response Types:** JSON Schema, RAML types, and OAS schemas
- **Security Schemes:** OAuth2, API key, basic auth, and custom schemes
- **Examples:** Request/response examples for testing and documentation
- **Deprecation:** API version lifecycle management

#### Example: Parsing RAML Specification

```python
# AgentFlow internally parses RAML like this:
# RAML specification sample:
# /customers:
#   get:
#     displayName: List Customers
#     queryParameters:
#       limit: integer
#       offset: integer
#     responses:
#       200:
#         body:
#           application/json:
#             type: array
#             items: Customer
#   post:
#     displayName: Create Customer
#     body:
#       application/json:
#         type: Customer

# Parsed to endpoint:
endpoint = {
    "id": "list-customers",
    "method": "GET",
    "path": "/customers",
    "display_name": "List Customers",
    "parameters": [
        {"name": "limit", "type": "integer", "in": "query"},
        {"name": "offset", "type": "integer", "in": "query"}
    ],
    "response_schema": {"type": "array", "items": "Customer"}
}
```

### Listing Discovered APIs

```python
# Get all discovered APIs
apis = connector.get_apis()

for api in apis:
    print(f"API: {api.name} v{api.version}")
    print(f"  Base URL: {api.base_url}")
    print(f"  Endpoints: {len(api.endpoints)}")
    for endpoint in api.endpoints:
        print(f"    - {endpoint.method} {endpoint.path}")
```

### Filtering APIs by Classification

```python
# Filter by group, status, or tags
financial_apis = connector.get_apis(group="Financial Services")
production_apis = connector.get_apis(tags=["production-ready"])
deprecated_apis = connector.get_apis(deprecated=True)
```

### Manual Cache Refresh

```python
# Force refresh of API catalog (useful after API deployments)
connector.refresh_api_catalog()
print("API catalog refreshed successfully")
```

---

## Runtime Orchestration

### Dynamic Router Integration

Discovered MuleSoft APIs are automatically registered with AgentFlow's **Dynamic Router**, which intelligently routes requests based on:

- **Target Environment:** Routes to the correct deployment (CloudHub vs. on-premises)
- **API Version:** Selects the appropriate API version based on constraints
- **Load Balancing:** Distributes traffic across multiple runtime instances
- **Health Status:** Avoids unhealthy or unavailable endpoints

### Request Routing Example

```python
from agentflow.orchestration import AgentOrchestrator
from agentflow.connectors.mulesoft import MuleSoftConnector, MuleSoftConfig

# Initialize connector and orchestrator
config = MuleSoftConfig(
    anypoint_url="https://anypoint.mulesoft.com",
    org_id="my-org-id",
    environment="production",
    client_id="client-id",
    client_secret="client-secret"
)

connector = MuleSoftConnector(config=config)
orchestrator = AgentOrchestrator()

# The Dynamic Router automatically routes to the discovered API:
response = orchestrator.invoke_api(
    api_id="customer-api",
    endpoint="/customers",
    method="GET",
    params={"limit": 10, "offset": 0},
    context={"environment": "production"}
)

print(f"Status: {response.status_code}")
print(f"Data: {response.json()}")
```

### Health Checks

AgentFlow continuously monitors the health of discovered MuleSoft APIs:

```python
# Health check configuration (automatic)
# Checks performed:
# 1. API availability on Anypoint Platform
# 2. CloudHub application status (if applicable)
# 3. Runtime instance responsiveness
# 4. Response time thresholds

# Manual health check
health = connector.check_api_health(api_id="customer-api")

print(f"Status: {health.status}")  # 'healthy', 'degraded', 'offline'
print(f"Last Check: {health.last_check_time}")
print(f"Response Time: {health.response_time_ms}ms")
```

### CloudHub Awareness

AgentFlow detects and optimizes routing for CloudHub-deployed APIs:

```python
# CloudHub detection (automatic if cloudHub_aware=True)
api_info = connector.get_api_info(api_id="customer-api")

if api_info.is_cloudHub_deployed:
    print(f"API running on CloudHub")
    print(f"  Workers: {api_info.cloudHub_workers}")
    print(f"  Region: {api_info.cloudHub_region}")
    print(f"  Capacity: {api_info.cloudHub_capacity}")
else:
    print(f"API running on-premises")
    print(f"  Runtime: {api_info.on_premises_runtime}")
    print(f"  Location: {api_info.on_premises_location}")
```

### Circuit Breaker Pattern

The Dynamic Router implements circuit breaker logic to handle API failures gracefully:

```python
# Automatic circuit breaking (transparent to caller)
# Circuit states:
# - CLOSED: Normal operation, requests pass through
# - OPEN: API failure threshold exceeded, requests fail fast
# - HALF_OPEN: Testing if API recovered, limited requests allowed

# Configuration
orchestrator.configure_circuit_breaker(
    api_id="customer-api",
    failure_threshold=5,
    failure_window_seconds=60,
    recovery_timeout_seconds=30,
    half_open_max_requests=3
)
```

---

## Authentication

### OAuth2 Client Credentials Flow

AgentFlow uses the OAuth2 Client Credentials flow to authenticate with Anypoint Platform:

1. **Initial Authentication:** Exchange client credentials for access token
2. **Token Caching:** Store token in memory cache with TTL
3. **Automatic Refresh:** Acquire new token before expiration
4. **Secure Storage:** Credentials stored in environment variables or secrets manager

### Authentication Flow Diagram

```
Client Credentials → Anypoint OAuth2 Server → Access Token
                                                     ↓
                                           Token Cache (TTL = 3600s)
                                                     ↓
                                    API Requests with Bearer Token
                                                     ↓
                                           (Token Expired?) → Refresh
```

### Token Caching Strategy

```python
# Token caching is automatic, but configurable:
config = MuleSoftConfig(
    anypoint_url="https://anypoint.mulesoft.com",
    org_id="my-org-id",
    environment="production",
    client_id="client-id",
    client_secret="client-secret",
    token_cache_ttl=3600  # Cache tokens for 1 hour
)

# Tokens are cached per:
# - Organization ID
# - Client ID
# - Environment
# Cache is automatically invalidated when TTL expires
```

### Manual Token Management

```python
# Retrieve current token info (without exposing the token itself)
token_info = connector.get_token_info()
print(f"Token Expires At: {token_info.expires_at}")
print(f"Time Remaining: {token_info.seconds_remaining}s")

# Force token refresh (useful before long-running operations)
connector.refresh_token()

# Check authentication status
if connector.is_authenticated():
    print("Successfully authenticated with Anypoint Platform")
else:
    print("Authentication failed")
```

### Secure Credential Storage

```python
# RECOMMENDED: Use environment variables
import os

config = MuleSoftConfig(
    anypoint_url=os.getenv("MULESOFT_ANYPOINT_URL"),
    org_id=os.getenv("MULESOFT_ORG_ID"),
    environment=os.getenv("MULESOFT_ENV"),
    client_id=os.getenv("MULESOFT_CLIENT_ID"),
    client_secret=os.getenv("MULESOFT_CLIENT_SECRET")
)

# RECOMMENDED: Use external secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
# Example with AWS Secrets Manager:
import boto3
import json

secrets_client = boto3.client('secretsmanager')
secret = secrets_client.get_secret_value(SecretId='mulesoft/prod')
creds = json.loads(secret['SecretString'])

config = MuleSoftConfig(
    anypoint_url=creds['anypoint_url'],
    org_id=creds['org_id'],
    environment=creds['environment'],
    client_id=creds['client_id'],
    client_secret=creds['client_secret']
)
```

---

## Advanced Patterns

### Multi-Environment Promotion

AgentFlow supports API promotion across development, staging, and production environments with intelligent routing:

```python
from agentflow.connectors.mulesoft import MuleSoftConnector, MuleSoftConfig
from agentflow.orchestration import AgentOrchestrator

# Define configs for each environment
env_configs = {
    "development": MuleSoftConfig(
        anypoint_url="https://anypoint.mulesoft.com",
        org_id="dev-org-id",
        environment="development",
        client_id="dev-client-id",
        client_secret="dev-client-secret"
    ),
    "staging": MuleSoftConfig(
        anypoint_url="https://anypoint.mulesoft.com",
        org_id="staging-org-id",
        environment="staging",
        client_id="staging-client-id",
        client_secret="staging-client-secret"
    ),
    "production": MuleSoftConfig(
        anypoint_url="https://anypoint.mulesoft.com",
        org_id="prod-org-id",
        environment="production",
        client_id="prod-client-id",
        client_secret="prod-client-secret"
    )
}

# Route based on context
def get_connector_for_env(env: str) -> MuleSoftConnector:
    config = env_configs[env]
    return MuleSoftConnector(config=config)

# Promote API from staging to production
def promote_api(api_id: str, from_env: str, to_env: str):
    from_connector = get_connector_for_env(from_env)
    to_connector = get_connector_for_env(to_env)
    
    # Get API spec from source environment
    api_spec = from_connector.get_api_spec(api_id)
    
    # Register in target environment
    promoted_api = to_connector.register_api(api_spec)
    
    print(f"Promoted {api_id} from {from_env} to {to_env}")
    print(f"New deployment URL: {promoted_api.base_url}")
    
    return promoted_api
```

### API Versioning

AgentFlow maintains and routes between multiple API versions intelligently:

```python
# Discover all versions of an API
customer_api_versions = connector.get_api_versions(api_id="customer-api")

for version in customer_api_versions:
    print(f"Version: {version.version_number}")
    print(f"  Status: {version.status}")  # 'stable', 'deprecated', 'beta'
    print(f"  Deployed: {version.deployment_date}")
    print(f"  Sunset Date: {version.sunset_date}")

# Route to specific version
response = orchestrator.invoke_api(
    api_id="customer-api",
    endpoint="/customers",
    method="GET",
    version="2.0",  # Explicit version selection
    context={"environment": "production"}
)

# Route to latest stable version (default)
response = orchestrator.invoke_api(
    api_id="customer-api",
    endpoint="/customers",
    method="GET",
    context={"environment": "production"}
)

# Gradual migration: Route percentage of traffic to new version
orchestrator.configure_traffic_shifting(
    api_id="customer-api",
    from_version="1.0",
    to_version="2.0",
    new_version_percentage=10  # Start with 10% of traffic
)
```

### Policy Compliance

AgentFlow respects MuleSoft API Manager policies during orchestration:

```python
# Auto-discover applied policies
policies = connector.get_api_policies(api_id="customer-api")

for policy in policies:
    print(f"Policy: {policy.name}")
    print(f"  Type: {policy.type}")  # 'rate-limit', 'throttle', 'cors', etc.
    print(f"  Status: {policy.status}")
    
    if policy.type == "rate-limit":
        print(f"    Requests: {policy.config.requests_per_period}")
        print(f"    Period: {policy.config.period}")

# Enforce policy limits in orchestrator
orchestrator.configure_policy_enforcement(
    api_id="customer-api",
    enforce_rate_limiting=True,
    enforce_throttling=True,
    enforce_cors=True
)

# Attempt API call that respects policies
try:
    response = orchestrator.invoke_api(
        api_id="customer-api",
        endpoint="/customers",
        method="GET",
        context={"environment": "production"}
    )
except RateLimitExceeded as e:
    print(f"Rate limit exceeded: {e.retry_after_seconds}s remaining")
except PolicyViolation as e:
    print(f"Policy violation: {e.policy_name}")
```

---

## Complete Example

### Scenario

Build an intelligent agent that:
1. Discovers customer and order APIs from MuleSoft Exchange
2. Handles a customer query: "Show me all orders for customer 12345"
3. Chains API calls: Get customer details → Retrieve orders → Enrich with product info
4. Respects rate limiting and handles failures gracefully

### Implementation

```python
"""
AgentFlow MuleSoft Integration - Complete Example
Orchestrates customer and order APIs from MuleSoft Anypoint Platform
"""

import os
import logging
from typing import Dict, List, Any
from datetime import datetime

from agentflow.connectors.mulesoft import MuleSoftConnector, MuleSoftConfig
from agentflow.orchestration import AgentOrchestrator, ExecutionContext
from agentflow.agents import Agent, AgentTask

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MuleSoftCustomerAgent(Agent):
    """
    Intelligent agent for customer and order management via MuleSoft APIs
    """
    
    def __init__(self):
        # Initialize MuleSoft connector with Anypoint Platform credentials
        config = MuleSoftConfig(
            anypoint_url=os.getenv("MULESOFT_ANYPOINT_URL", "https://anypoint.mulesoft.com"),
            org_id=os.getenv("MULESOFT_ORG_ID"),
            environment=os.getenv("MULESOFT_ENV", "production"),
            client_id=os.getenv("MULESOFT_CLIENT_ID"),
            client_secret=os.getenv("MULESOFT_CLIENT_SECRET"),
            api_discovery_interval=1800,  # Refresh API catalog every 30 minutes
            token_cache_ttl=3600,  # Cache tokens for 1 hour
            cloudHub_aware=True
        )
        
        self.connector = MuleSoftConnector(config=config)
        self.orchestrator = AgentOrchestrator()
        
        # Discover APIs on initialization
        self._discover_apis()
        
        super().__init__(
            name="MuleSoft Customer Agent",
            description="Orchestrates customer and order APIs via MuleSoft"
        )
    
    def _discover_apis(self):
        """Discover and register MuleSoft APIs"""
        logger.info("Discovering MuleSoft APIs...")
        
        apis = self.connector.get_apis()
        logger.info(f"Discovered {len(apis)} APIs")
        
        for api in apis:
            logger.info(f"  - {api.name} v{api.version} ({len(api.endpoints)} endpoints)")
            for endpoint in api.endpoints:
                logger.debug(f"      {endpoint.method} {endpoint.path}")
    
    def get_customer_details(self, customer_id: str) -> Dict[str, Any]:
        """
        Retrieve customer details from MuleSoft Customer API
        
        Args:
            customer_id: Unique customer identifier
            
        Returns:
            Customer details dictionary
        """
        logger.info(f"Fetching customer details for ID: {customer_id}")
        
        context = ExecutionContext(
            environment="production",
            trace_id=f"customer-{customer_id}-{datetime.now().isoformat()}"
        )
        
        response = self.orchestrator.invoke_api(
            api_id="customer-api",
            endpoint=f"/customers/{customer_id}",
            method="GET",
            context=context
        )
        
        if response.status_code == 200:
            customer = response.json()
            logger.info(f"Retrieved customer: {customer.get('name', 'Unknown')}")
            return customer
        else:
            logger.error(f"Failed to get customer: {response.status_code}")
            raise Exception(f"Customer API error: {response.status_code}")
    
    def get_customer_orders(self, customer_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve orders for a customer from MuleSoft Order API
        
        Args:
            customer_id: Unique customer identifier
            limit: Maximum number of orders to retrieve
            
        Returns:
            List of order dictionaries
        """
        logger.info(f"Fetching orders for customer ID: {customer_id} (limit: {limit})")
        
        context = ExecutionContext(
            environment="production",
            trace_id=f"orders-{customer_id}-{datetime.now().isoformat()}"
        )
        
        response = self.orchestrator.invoke_api(
            api_id="order-api",
            endpoint=f"/customers/{customer_id}/orders",
            method="GET",
            params={
                "limit": limit,
                "sort": "-created_date"  # Latest first
            },
            context=context
        )
        
        if response.status_code == 200:
            orders = response.json()
            logger.info(f"Retrieved {len(orders)} orders")
            return orders
        else:
            logger.error(f"Failed to get orders: {response.status_code}")
            raise Exception(f"Order API error: {response.status_code}")
    
    def get_product_details(self, product_id: str) -> Dict[str, Any]:
        """
        Retrieve product details from MuleSoft Product API
        
        Args:
            product_id: Unique product identifier
            
        Returns:
            Product details dictionary
        """
        logger.debug(f"Fetching product details for ID: {product_id}")
        
        context = ExecutionContext(environment="production")
        
        response = self.orchestrator.invoke_api(
            api_id="product-api",
            endpoint=f"/products/{product_id}",
            method="GET",
            context=context
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Failed to get product {product_id}: {response.status_code}")
            return {"id": product_id, "name": "Unknown Product"}
    
    def enrich_orders_with_products(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich order data with product information
        
        Args:
            orders: List of order dictionaries
            
        Returns:
            Orders enriched with product details
        """
        logger.info(f"Enriching {len(orders)} orders with product details...")
        
        for order in orders:
            if "items" in order:
                for item in order["items"]:
                    product = self.get_product_details(item.get("product_id"))
                    item["product_name"] = product.get("name", "Unknown")
                    item["product_price"] = product.get("price", 0)
        
        return orders
    
    def handle_customer_query(self, customer_id: str) -> Dict[str, Any]:
        """
        Main agent task: Handle a customer query
        Chains together multiple API calls to provide comprehensive response
        
        Args:
            customer_id: ID of the customer to query
            
        Returns:
            Comprehensive response with customer and order data
        """
        logger.info(f"Processing customer query for ID: {customer_id}")
        
        try:
            # Step 1: Get customer details
            customer = self.get_customer_details(customer_id)
            
            # Step 2: Get customer's orders
            orders = self.get_customer_orders(customer_id, limit=10)
            
            # Step 3: Enrich orders with product information
            enriched_orders = self.enrich_orders_with_products(orders)
            
            # Step 4: Compile response
            result = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "customer": {
                    "id": customer.get("id"),
                    "name": customer.get("name"),
                    "email": customer.get("email"),
                    "phone": customer.get("phone"),
                    "status": customer.get("status")
                },
                "orders": {
                    "count": len(enriched_orders),
                    "total_value": sum(o.get("total", 0) for o in enriched_orders),
                    "orders": enriched_orders
                }
            }
            
            logger.info(f"Successfully processed query for customer {customer_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing customer query: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Check health of all discovered APIs
        
        Returns:
            Health status for each API
        """
        logger.info("Checking API health status...")
        
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "connector": "online" if self.connector.is_authenticated() else "offline",
            "apis": {}
        }
        
        apis = self.connector.get_apis()
        
        for api in apis:
            try:
                health = self.connector.check_api_health(api.id)
                health_report["apis"][api.name] = {
                    "status": health.status,
                    "response_time_ms": health.response_time_ms,
                    "last_check": health.last_check_time.isoformat()
                }
            except Exception as e:
                health_report["apis"][api.name] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return health_report


# Main execution
if __name__ == "__main__":
    # Initialize the agent
    agent = MuleSoftCustomerAgent()
    
    # Example 1: Handle a customer query
    print("\n" + "="*70)
    print("EXAMPLE: Customer Order Query")
    print("="*70)
    
    result = agent.handle_customer_query(customer_id="12345")
    
    print("\nQuery Result:")
    print(f"  Customer: {result['customer']['name']} ({result['customer']['email']})")
    print(f"  Orders: {result['orders']['count']}")
    print(f"  Total Value: ${result['orders']['total_value']:.2f}")
    
    for order in result['orders']['orders'][:3]:  # Show first 3 orders
        print(f"\n  Order #{order['order_number']}")
        print(f"    Date: {order['created_date']}")
        print(f"    Status: {order['status']}")
        print(f"    Total: ${order['total']:.2f}")
        for item in order.get('items', [])[:2]:  # Show first 2 items
            print(f"      - {item['product_name']} (Qty: {item['quantity']})")
    
    # Example 2: Check API health
    print("\n" + "="*70)
    print("EXAMPLE: API Health Check")
    print("="*70)
    
    health = agent.get_health_status()
    
    print(f"\nConnector Status: {health['connector']}")
    print("\nAPI Health:")
    for api_name, api_health in health['apis'].items():
        status = api_health.get('status', 'unknown')
        response_time = api_health.get('response_time_ms', 'N/A')
        print(f"  {api_name}: {status} ({response_time}ms)")
```

### Running the Example

```bash
# Set environment variables
export MULESOFT_ANYPOINT_URL="https://anypoint.mulesoft.com"
export MULESOFT_ORG_ID="your-org-uuid"
export MULESOFT_ENV="production"
export MULESOFT_CLIENT_ID="your-client-id"
export MULESOFT_CLIENT_SECRET="your-client-secret"

# Run the agent
python mulesoft_agent_example.py
```

### Expected Output

```
EXAMPLE: Customer Order Query
======================================================================

Query Result:
  Customer: John Smith (john.smith@example.com)
  Orders: 12
  Total Value: $4,329.50

  Order #ORD-2026-001
    Date: 2026-04-10
    Status: completed
    Total: $425.00
      - Professional Laptop (Qty: 1)
      - Wireless Mouse (Qty: 2)

  Order #ORD-2026-002
    Date: 2026-04-08
    Status: in_transit
    Total: $89.99
      - USB-C Cable (Qty: 3)

======================================================================
EXAMPLE: API Health Check
======================================================================

Connector Status: online

API Health:
  customer-api: healthy (45ms)
  order-api: healthy (52ms)
  product-api: degraded (145ms)
```

---

## Best Practices

1. **Credential Management:** Always store Anypoint Platform credentials in environment variables or a secrets manager, never hardcode them.

2. **Token Caching:** Configure appropriate `token_cache_ttl` values based on your security requirements (higher TTL = better performance, lower TTL = better security).

3. **API Discovery:** Schedule periodic `refresh_api_catalog()` calls after deploying new APIs to Anypoint Exchange.

4. **Error Handling:** Implement comprehensive error handling for network failures, rate limiting, and policy violations.

5. **Monitoring:** Monitor API health via `check_api_health()` and log execution traces for debugging.

6. **Environment Isolation:** Use separate Anypoint organization IDs or environments for dev/staging/production to prevent accidental changes.

7. **Version Management:** Always specify target API versions explicitly when versioning is critical to your workflow.

8. **Circuit Breaker:** Configure circuit breaker thresholds conservatively to prevent cascading failures.

---

## Troubleshooting

### Authentication Failures

- **Symptom:** "Authentication failed with Anypoint Platform"
- **Solution:** Verify `client_id` and `client_secret` are correct and have valid permissions in Anypoint Access Management

### API Discovery Issues

- **Symptom:** "No APIs discovered"
- **Solution:** Check that APIs are published to Anypoint Exchange and your service account has read permissions

### Rate Limiting

- **Symptom:** "Rate limit exceeded" errors
- **Solution:** Implement exponential backoff retry logic or request rate limit increases from your MuleSoft administrator

### CloudHub Routing

- **Symptom:** "Unable to reach CloudHub application"
- **Solution:** Verify CloudHub application is deployed and running; check worker allocation and region configuration

---

## References

- [MuleSoft Anypoint Platform Documentation](https://docs.mulesoft.com/general/)
- [Anypoint Exchange API](https://docs.mulesoft.com/exchange/exchange-api-documentation)
- [API Manager Policies](https://docs.mulesoft.com/api-manager/policies-landing-page)
- [CloudHub Deployment](https://docs.mulesoft.com/cloudhub/getting-started-with-cloudhub)
- [OAuth2 in Anypoint](https://docs.mulesoft.com/access-management/external-identity)

---

**Document Version:** 1.0  
**Last Modified:** April 2026  
**Author:** Venkata Pavan Kumar Gummadi
