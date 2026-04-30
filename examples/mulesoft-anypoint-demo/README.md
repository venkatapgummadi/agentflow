# AgentFlow — MuleSoft Anypoint Studio Demo

[![MuleSoft Runtime](https://img.shields.io/badge/Mule%20Runtime-4.6.0-blue)](https://www.mulesoft.com)
[![AgentFlow](https://img.shields.io/badge/AgentFlow-1.0.0-teal)](https://github.com/venkatapgummadi/agentflow)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](../../LICENSE)

A production-ready **MuleSoft Anypoint Studio** integration that bridges the Anypoint Platform with [AgentFlow](https://github.com/venkatapgummadi/agentflow) — the open-source AI-powered multi-agent API orchestration framework.

## What This Does

This Mule application exposes a clean REST API (defined in RAML 1.0) that forwards orchestration intents to the AgentFlow Python engine. Instead of writing custom DataWeave transformations and HTTP flows for every integration, you describe what you want in plain English — AgentFlow's agents handle the rest.

```
Anypoint Studio App
        │
        │  POST /agentflow/api/v1/orchestrate
        │  { "intent": "Fetch customer 12345, check credit, create loan if score > 700" }
        ▼
  AgentFlow Engine (Python)
        │
        ├─ PlannerAgent  → builds DAG from intent
        ├─ ExecutorAgent → runs API calls in parallel
        └─ ValidatorAgent → checks results
        │
        ▼
  JSON response with outputs + validation + execution trace
```

## Project Structure

```
mulesoft-anypoint-demo/
├── src/main/
│   ├── api/
│   │   └── agentflow-api.raml          # RAML 1.0 API specification
│   ├── mule/
│   │   ├── agentflow-main.xml          # Main flows (orchestrate, health, apis)
│   │   └── agentflow-error-handler.xml # Global error handling
│   └── resources/
│       ├── config.yaml                 # Property placeholders
│       └── local.properties            # Local dev values (do not commit)
├── mule-artifact.json                  # Mule app descriptor
└── pom.xml                             # Maven build + CloudHub deploy config
```

## Prerequisites

- **Anypoint Studio 7.x** — [Download](https://www.mulesoft.com/platform/studio)
- **Java 17** (required for Mule 4.6)
- **AgentFlow Python engine** running locally or on a server
  ```bash
  # From the agentflow repo root:
  pip install -e ".[all]"
  uvicorn agentflow.server:app --host 0.0.0.0 --port 8000
  ```
- **MuleSoft Anypoint account** (free tier works) — [Sign up](https://anypoint.mulesoft.com)

## Quick Start

### 1. Clone and import into Anypoint Studio

```bash
git clone https://github.com/venkatapgummadi/agentflow.git
```

In Anypoint Studio: **File → Import → Anypoint Studio → Maven-based Mule Project from pom.xml**
Select: `examples/mulesoft-anypoint-demo/pom.xml`

### 2. Configure properties

Copy `src/main/resources/local.properties` and fill in your values:

```properties
http.port=8081
agentflow.host=localhost
agentflow.port=8000
agentflow.protocol=http
anypoint.client_id=YOUR_CLIENT_ID
anypoint.client_secret=YOUR_CLIENT_SECRET
```

In Anypoint Studio: Right-click project → **Run As → Mule Application**
Add VM argument: `-M-Dmule.env=local`

### 3. Test it

```bash
# Health check
curl http://localhost:8081/agentflow/api/v1/health

# Submit an orchestration intent
curl -X POST http://localhost:8081/agentflow/api/v1/orchestrate \
  -H "Content-Type: application/json" \
  -H "client_id: YOUR_CLIENT_ID" \
  -H "client_secret: YOUR_CLIENT_SECRET" \
  -d '{
    "intent": "Fetch customer profile from CRM and check their payment history",
    "parameters": { "customer_id": "C-12345" },
    "timeout_ms": 15000,
    "trace": true
  }'
```

**Example response:**
```json
{
  "execution_id": "exec-a1b2c3d4",
  "intent": "Fetch customer profile from CRM and check their payment history",
  "status": "completed",
  "steps_executed": 2,
  "steps_succeeded": 2,
  "duration_ms": 634,
  "outputs": {
    "fetch_customer_profile": { "id": "C-12345", "name": "Jane Smith" },
    "check_payment_history":  { "on_time_rate": 0.98, "risk": "low" }
  },
  "validation": { "passed": true, "errors": [], "warnings": [] }
}
```

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agentflow/api/v1/orchestrate` | Submit an orchestration intent |
| `GET`  | `/agentflow/api/v1/orchestrate/{executionId}` | Retrieve execution result |
| `GET`  | `/agentflow/api/v1/health` | Health check |
| `GET`  | `/agentflow/api/v1/apis` | List discovered API endpoints |

Full RAML spec: [`src/main/api/agentflow-api.raml`](src/main/api/agentflow-api.raml)

## Deploy to CloudHub

```bash
mvn clean deploy -DskipTests \
  -Danypoint.username=YOUR_USERNAME \
  -Danypoint.password=YOUR_PASSWORD \
  -Danypoint.environment=Sandbox \
  -Danypoint.target=Shared Space
```

Or use **Anypoint Studio → Run → Deploy to Anypoint Platform**.

## Example Use Cases

| Use Case | Example Intent |
|---|---|
| **FinTech** | `"Fetch customer from Salesforce, check Experian credit score, pre-approve loan if > 700"` |
| **HealthTech** | `"Get patient FHIR record, verify insurance eligibility, schedule cardiology referral"` |
| **eCommerce** | `"Check inventory across 3 warehouses, reserve stock, create fulfillment order"` |
| **Compliance** | `"Run KYC check on customer, screen against OFAC list, log to audit trail"` |

More examples in [`examples/`](../) of the AgentFlow repository.

## How It Works

```
POST /orchestrate
       │
       ▼
  DataWeave Transform
  (enrich + add source=mulesoft-anypoint)
       │
       ▼
  HTTP Request → AgentFlow Engine
       │
       ├── PlannerAgent
       │     └── Decomposes intent into DAG steps
       │
       ├── ExecutorAgent
       │     ├── Runs parallel steps with semaphore bounding
       │     ├── DynamicRouter scores endpoints: latency + cost + rate-limit + health
       │     └── CircuitBreaker protects each endpoint
       │
       └── ValidatorAgent
             └── Checks completeness, data presence, custom rules
       │
       ▼
  DataWeave Transform (map to RAML contract)
       │
       ▼
  HTTP Response
```

## Publish to Anypoint Exchange

1. Add your Organization ID to `pom.xml` (replace `com.agentflow.mulesoft` groupId)
2. Tag with: `ai`, `orchestration`, `api-management`, `mulesoft`, `agentflow`
3. Run: `mvn clean deploy -DskipTests`

Your asset will appear in **Anypoint Exchange** for your org's developers.

## Contributing

Found a bug or want to add a connector example? Open an issue or PR in the main [AgentFlow repo](https://github.com/venkatapgummadi/agentflow).

## Author

**Venkata Pavan Kumar Gummadi** — Principal MuleSoft Architect  
[GitHub](https://github.com/venkatapgummadi) · [LinkedIn](https://www.linkedin.com/in/venkata-p-1841146/)  
*Architecture lead — Broadridge Wealth InFocus (2025 Datos Impact Award)*

## License

Apache License 2.0 — see [LICENSE](../../LICENSE)
