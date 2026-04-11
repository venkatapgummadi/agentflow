# Custom Agents Guide

**Author:** Venkata Pavan Kumar Gummadi

## 1. Overview

AgentFlow is built on a composable agent-based architecture where agents are autonomous, reusable components that execute domain-specific logic within an orchestrated workflow. The core abstraction is the **BaseAgent ABC** (Abstract Base Class), which defines the contract for all agents in the framework.

Agents in AgentFlow:
- Execute discrete business logic in isolation
- Communicate via a shared `OrchestrationContext` (blackboard pattern)
- Emit events for audit trails and observability
- Support parallel execution, conditional routing, and error handling
- Can be chained together to form complex multi-agent workflows

This guide walks you through understanding AgentFlow's agent model, using built-in agents, and creating custom agents for your domain.

---

## 2. BaseAgent Interface

All agents in AgentFlow inherit from the `BaseAgent` abstract base class. Understanding this interface is crucial for building custom agents.

### BaseAgent ABC

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass

@dataclass
class AgentExecutionResult:
    """Result of agent execution"""
    success: bool
    output: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

class BaseAgent(ABC):
    """Base class for all agents in AgentFlow"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.event_journal = []
    
    @abstractmethod
    def execute(self, context: 'OrchestrationContext', **kwargs) -> AgentExecutionResult:
        """
        Execute the agent's core logic.
        
        Args:
            context: Shared orchestration context (blackboard)
            **kwargs: Agent-specific parameters
            
        Returns:
            AgentExecutionResult with success status and output
        """
        pass
    
    def emit_event(self, event_type: str, data: Dict[str, Any]):
        """
        Emit an event for audit trail and observability.
        
        Args:
            event_type: Type of event (e.g., 'execution_started', 'validation_passed')
            data: Event payload containing relevant details
        """
        event = {
            'agent': self.name,
            'type': event_type,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        self.event_journal.append(event)
        # Also add to context's global event journal for orchestration-level tracking
        context.event_journal.append(event)
```

### Key Concepts

**Agent Name:**
- Uniquely identifies an agent in the workflow
- Used for routing, logging, and event tracking
- Should be descriptive (e.g., `fraud_detector`, `clinical_decision_engine`)

**execute() Method:**
- The core contract all agents must implement
- Receives the shared `OrchestrationContext` for data access and sharing
- Accepts `**kwargs` for agent-specific parameters
- Returns `AgentExecutionResult` with success status and output

**emit_event():**
- Records events in the agent's local journal and global context
- Enables audit trails, debugging, and compliance tracking
- Events include timestamp, agent name, event type, and payload

---

## 3. Built-in Agents

AgentFlow includes three foundational agents for common patterns:

### 3.1 PlannerAgent

The `PlannerAgent` analyzes capabilities, matches them to requirements, and creates execution plans.

**Use Case:** When you have multiple agents available and need to determine which to invoke and in what order.

```python
from agentflow.agents import PlannerAgent

planner = PlannerAgent(
    name="orchestration_planner",
    available_agents=[
        fraudDetector,
        riskScorer,
        decisionEngine
    ]
)

result = planner.execute(
    context,
    user_request="Detect fraud and score risk for transaction 12345",
    requirements=["fraud_detection", "risk_scoring"]
)

if result.success:
    plan = result.output  # List of agent execution steps
    print(f"Execution plan: {plan}")
```

**Key Features:**
- Analyzes agent capabilities
- Creates DAG-based execution plans
- Supports conditional branches
- Returns ordered list of agents to execute

### 3.2 ExecutorAgent

The `ExecutorAgent` manages parallel execution of multiple agents using a DAG with semaphore bounding.

**Use Case:** When you need to run multiple agents concurrently while controlling resource usage.

```python
from agentflow.agents import ExecutorAgent

executor = ExecutorAgent(
    name="parallel_executor",
    max_parallel_tasks=3  # Semaphore: max 3 concurrent executions
)

execution_plan = [
    ("fraud_detector", {"transaction_id": "12345"}),
    ("risk_scorer", {"transaction_id": "12345"}),
    ("compliance_checker", {"transaction_id": "12345"})
]

result = executor.execute(context, plan=execution_plan)

if result.success:
    results = result.output  # Dict mapping agent names to their results
    print(f"Execution results: {results}")
```

**Key Features:**
- Executes agents in parallel using asyncio or threading
- Semaphore-based concurrency control
- Dependency tracking (if agents have inter-dependencies)
- Aggregates results from all agents
- Handles failures with configurable rollback

### 3.3 ValidatorAgent

The `ValidatorAgent` applies rule-based validation to context data.

**Use Case:** When you need to validate outputs or state against business rules before proceeding.

```python
from agentflow.agents import ValidatorAgent

validator = ValidatorAgent(name="business_rule_validator")

validation_rules = [
    ("customer_age >= 18", "Must be adult"),
    ("account_status == 'active'", "Account must be active"),
    ("transaction_amount <= daily_limit", "Exceeds daily limit")
]

result = validator.execute(
    context,
    rules=validation_rules,
    context_data={
        'customer_age': 25,
        'account_status': 'active',
        'transaction_amount': 5000,
        'daily_limit': 10000
    }
)

if result.success:
    violations = result.output  # List of rule violations (empty if valid)
    print(f"Validation passed: {len(violations) == 0}")
```

**Key Features:**
- Evaluates rule expressions against context
- Returns list of violations (empty if all rules pass)
- Supports complex boolean expressions
- Integrates with audit trails

---

## 4. Writing a Custom Agent

Creating a custom agent is straightforward. Here's a step-by-step walkthrough with a concrete example: a **FraudDetectionAgent**.

### 4.1 Step 1: Define the Agent Class

```python
from agentflow.agents import BaseAgent, AgentExecutionResult
from typing import Dict, Any, Optional
import logging

class FraudDetectionAgent(BaseAgent):
    """
    Detects fraudulent transactions using multiple heuristics:
    - Transaction amount anomalies
    - Geographic velocity checks
    - Spending pattern deviations
    """
    
    def __init__(self, name: str = "fraud_detector", 
                 anomaly_threshold: float = 0.8,
                 velocity_check: bool = True):
        super().__init__(name, description="Detects fraudulent transactions")
        self.anomaly_threshold = anomaly_threshold
        self.velocity_check = velocity_check
        self.logger = logging.getLogger(self.name)
```

### 4.2 Step 2: Implement the execute() Method

```python
    def execute(self, context: 'OrchestrationContext', **kwargs) -> AgentExecutionResult:
        """
        Execute fraud detection logic.
        
        Args:
            context: Shared orchestration context
            **kwargs: 
                - transaction_id: ID of transaction to check
                - customer_id: ID of customer
                - amount: Transaction amount
                - merchant_category: Merchant category code
        
        Returns:
            AgentExecutionResult with fraud_score (0-1) and risk_factors
        """
        try:
            # Extract parameters
            transaction_id = kwargs.get('transaction_id')
            customer_id = kwargs.get('customer_id')
            amount = kwargs.get('amount')
            merchant_category = kwargs.get('merchant_category')
            
            self.emit_event('execution_started', {
                'transaction_id': transaction_id,
                'customer_id': customer_id
            })
            
            # Validation
            if not all([transaction_id, customer_id, amount]):
                return AgentExecutionResult(
                    success=False,
                    output=None,
                    error="Missing required parameters: transaction_id, customer_id, amount"
                )
            
            # Retrieve customer history from context (shared blackboard)
            customer_history = context.get_data(f'customer_{customer_id}_history')
            if not customer_history:
                self.logger.warning(f"No history found for customer {customer_id}")
                customer_history = {}
            
            # Run fraud detection heuristics
            fraud_score = 0.0
            risk_factors = []
            
            # Check 1: Amount anomaly
            amount_anomaly = self._check_amount_anomaly(amount, customer_history)
            if amount_anomaly > self.anomaly_threshold:
                fraud_score += 0.4
                risk_factors.append(f"Amount anomaly detected (score: {amount_anomaly:.2f})")
            
            # Check 2: Velocity check
            if self.velocity_check:
                velocity_risk = self._check_spending_velocity(
                    customer_id, amount, customer_history
                )
                if velocity_risk > self.anomaly_threshold:
                    fraud_score += 0.3
                    risk_factors.append(f"High spending velocity (risk: {velocity_risk:.2f})")
            
            # Check 3: Merchant category check
            category_risk = self._check_merchant_category(merchant_category)
            if category_risk > 0.5:
                fraud_score += 0.2
                risk_factors.append(f"High-risk merchant category: {merchant_category}")
            
            # Clamp fraud_score to [0, 1]
            fraud_score = min(1.0, fraud_score)
            
            # Store result in context for other agents
            context.set_data(f'transaction_{transaction_id}_fraud_score', fraud_score)
            context.set_data(f'transaction_{transaction_id}_risk_factors', risk_factors)
            
            # Emit completion event
            self.emit_event('execution_completed', {
                'transaction_id': transaction_id,
                'fraud_score': fraud_score,
                'risk_factors': risk_factors
            })
            
            return AgentExecutionResult(
                success=True,
                output={
                    'fraud_score': fraud_score,
                    'risk_factors': risk_factors,
                    'transaction_id': transaction_id,
                    'recommendation': 'block' if fraud_score > 0.7 else 'allow'
                },
                metadata={'checks_performed': 3}
            )
        
        except Exception as e:
            self.logger.error(f"Fraud detection failed: {str(e)}")
            self.emit_event('execution_failed', {'error': str(e)})
            return AgentExecutionResult(
                success=False,
                output=None,
                error=f"Fraud detection error: {str(e)}"
            )
```

### 4.3 Step 3: Implement Helper Methods

```python
    def _check_amount_anomaly(self, amount: float, history: Dict) -> float:
        """
        Check if transaction amount is anomalous compared to history.
        Returns anomaly score [0, 1].
        """
        if not history.get('transactions'):
            return 0.0
        
        amounts = [t['amount'] for t in history['transactions'][-30:]]  # Last 30 txns
        avg_amount = sum(amounts) / len(amounts)
        std_dev = (sum((x - avg_amount) ** 2 for x in amounts) / len(amounts)) ** 0.5
        
        if std_dev == 0:
            return 0.0
        
        z_score = abs(amount - avg_amount) / std_dev
        # Convert z-score to [0, 1] probability
        return min(1.0, z_score / 4.0)
    
    def _check_spending_velocity(self, customer_id: str, amount: float, 
                                 history: Dict) -> float:
        """
        Check if customer is spending unusually fast.
        Returns velocity risk score [0, 1].
        """
        recent_total = sum(
            t['amount'] for t in history.get('transactions', [])[-5:]  # Last 5 txns
        )
        if recent_total == 0:
            return 0.0
        velocity = (recent_total + amount) / recent_total
        return min(1.0, (velocity - 1.0) / 2.0)  # 0-1 scale
    
    def _check_merchant_category(self, category: str) -> float:
        """
        Risk score for merchant category.
        """
        high_risk_categories = {
            'money_transfer': 0.8,
            'crypto': 0.9,
            'gambling': 0.7,
            'adult': 0.7
        }
        return high_risk_categories.get(category, 0.1)
```

### 4.4 Complete Example: FraudDetectionAgent

```python
from agentflow.agents import BaseAgent, AgentExecutionResult
from agentflow.context import OrchestrationContext
import logging
from datetime import datetime

class FraudDetectionAgent(BaseAgent):
    """Detects fraudulent transactions using heuristic rules."""
    
    def __init__(self, name: str = "fraud_detector", 
                 anomaly_threshold: float = 0.8):
        super().__init__(name, "Detects fraudulent transactions")
        self.anomaly_threshold = anomaly_threshold
        self.logger = logging.getLogger(self.name)
    
    def execute(self, context: OrchestrationContext, **kwargs) -> AgentExecutionResult:
        try:
            transaction_id = kwargs.get('transaction_id')
            customer_id = kwargs.get('customer_id')
            amount = kwargs.get('amount')
            
            self.emit_event('fraud_check_started', {'transaction_id': transaction_id})
            
            # Retrieve customer history from shared context
            history = context.get_data(f'customer_{customer_id}_history') or {}
            
            # Calculate fraud score (0-1, where 1 = highest fraud risk)
            fraud_score = self._calculate_fraud_score(amount, history)
            
            # Store result in context for downstream agents
            context.set_data(f'transaction_{transaction_id}_fraud_score', fraud_score)
            
            self.emit_event('fraud_check_completed', {
                'transaction_id': transaction_id,
                'fraud_score': fraud_score
            })
            
            return AgentExecutionResult(
                success=True,
                output={
                    'fraud_score': fraud_score,
                    'recommendation': 'block' if fraud_score > 0.7 else 'allow'
                }
            )
        except Exception as e:
            return AgentExecutionResult(
                success=False,
                output=None,
                error=str(e)
            )
    
    def _calculate_fraud_score(self, amount: float, history: Dict) -> float:
        """Calculate fraud risk score based on transaction amount and history."""
        if not history.get('transactions'):
            return 0.0
        
        amounts = [t['amount'] for t in history['transactions'][-30:]]
        avg = sum(amounts) / len(amounts)
        std = (sum((x - avg) ** 2 for x in amounts) / len(amounts)) ** 0.5
        
        if std == 0:
            return 0.0
        
        z_score = abs(amount - avg) / std
        return min(1.0, z_score / 4.0)
```

---

## 5. Agent Communication

AgentFlow agents communicate through the **OrchestrationContext**, which acts as a shared blackboard. This pattern enables loose coupling and supports complex orchestration scenarios.

### 5.1 OrchestrationContext

```python
class OrchestrationContext:
    """Shared blackboard for agent communication and state management."""
    
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.data_store = {}      # Shared key-value store
        self.event_journal = []    # Global event log
        self.metadata = {}         # Workflow metadata
    
    def set_data(self, key: str, value: Any):
        """Store data in the shared context."""
        self.data_store[key] = value
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """Retrieve data from the shared context."""
        return self.data_store.get(key, default)
    
    def get_all_data(self) -> Dict[str, Any]:
        """Retrieve all data in the context."""
        return self.data_store.copy()
    
    def delete_data(self, key: str):
        """Remove data from the context."""
        self.data_store.pop(key, None)
```

### 5.2 Example: Agent Coordination

```python
# Initialize shared context
context = OrchestrationContext(workflow_id="txn_workflow_001")

# Agent 1: FraudDetector reads transaction and stores fraud_score
fraud_detector = FraudDetectionAgent()
result1 = fraud_detector.execute(
    context,
    transaction_id="TXN_123",
    customer_id="CUST_456",
    amount=5000
)

# Agent 2: RiskScorer reads fraud_score and computes risk level
risk_scorer = RiskScoringAgent()
fraud_score = context.get_data('transaction_TXN_123_fraud_score')
result2 = risk_scorer.execute(
    context,
    transaction_id="TXN_123",
    fraud_score=fraud_score  # Passed from previous agent via context
)

# Agent 3: DecisionEngine reads both fraud_score and risk_level
decision_engine = DecisionEngineAgent()
risk_level = context.get_data('transaction_TXN_123_risk_level')
result3 = decision_engine.execute(
    context,
    transaction_id="TXN_123",
    fraud_score=fraud_score,
    risk_level=risk_level
)

# Access audit trail
print("Event Journal:")
for event in context.event_journal:
    print(f"  {event['agent']}: {event['type']} at {event['timestamp']}")
```

### 5.3 Data Naming Convention

To avoid collisions, use prefixed keys:
- `transaction_{transaction_id}_{attribute}` — Transaction-specific data
- `customer_{customer_id}_{attribute}` — Customer-specific data
- `workflow_{workflow_id}_{state}` — Workflow state

```python
# Good naming
context.set_data('transaction_TXN_123_fraud_score', 0.85)
context.set_data('customer_CUST_456_history', {...})
context.set_data('workflow_WF_001_status', 'in_progress')

# Bad naming (collision risk)
context.set_data('fraud_score', 0.85)  # Ambiguous
context.set_data('status', 'in_progress')  # Too generic
```

---

## 6. Advanced Patterns

### 6.1 Agent Chaining

Chain multiple agents in sequence, with each agent reading and writing to the shared context.

```python
class OrchestrationPipeline:
    """Executes a sequence of agents with dependency management."""
    
    def __init__(self, agents: List[Tuple[BaseAgent, Dict]]):
        self.agents = agents  # List of (agent, config) tuples
    
    def execute(self, context: OrchestrationContext) -> Dict[str, AgentExecutionResult]:
        results = {}
        
        for agent, config in self.agents:
            self.logger.info(f"Executing {agent.name}")
            
            # Pass config kwargs to agent
            result = agent.execute(context, **config)
            results[agent.name] = result
            
            if not result.success and config.get('fail_fast', True):
                self.logger.error(f"Agent {agent.name} failed: {result.error}")
                break
        
        return results

# Usage
pipeline = OrchestrationPipeline([
    (FraudDetectionAgent(), {
        'transaction_id': 'TXN_123',
        'customer_id': 'CUST_456',
        'amount': 5000
    }),
    (RiskScoringAgent(), {
        'transaction_id': 'TXN_123',
        'fail_fast': False  # Continue even if this agent fails
    }),
    (DecisionEngineAgent(), {
        'transaction_id': 'TXN_123'
    })
])

results = pipeline.execute(context)
```

### 6.2 Conditional Execution

Route execution based on context state or previous results.

```python
class ConditionalRouter(BaseAgent):
    """Routes to different agents based on conditions."""
    
    def __init__(self, conditions: Dict[str, BaseAgent]):
        super().__init__("conditional_router", "Routes to agents based on conditions")
        self.conditions = conditions  # Map of (condition -> agent)
    
    def execute(self, context: OrchestrationContext, **kwargs) -> AgentExecutionResult:
        for condition, agent in self.conditions.items():
            if self._evaluate_condition(condition, context):
                self.emit_event('condition_matched', {'condition': condition})
                return agent.execute(context, **kwargs)
        
        self.emit_event('no_conditions_matched', {})
        return AgentExecutionResult(success=True, output=None)
    
    def _evaluate_condition(self, condition: str, context: OrchestrationContext) -> bool:
        # Example: condition = "fraud_score > 0.7"
        return eval(condition, {'context': context.get_all_data()})

# Usage
router = ConditionalRouter({
    'fraud_score > 0.7': BlockTransactionAgent(),
    'fraud_score > 0.3': ManualReviewAgent(),
    'fraud_score <= 0.3': ApproveTransactionAgent()
})

fraud_score = context.get_data('transaction_TXN_123_fraud_score')
context.set_data('fraud_score', fraud_score)  # For condition evaluation
result = router.execute(context, transaction_id='TXN_123')
```

### 6.3 Error Handling and Rollback

Implement graceful degradation and rollback on failure.

```python
class ResilientOrchestrator(BaseAgent):
    """Orchestrates agents with error handling and rollback."""
    
    def __init__(self, agents: List[BaseAgent], rollback_enabled: bool = True):
        super().__init__("resilient_orchestrator")
        self.agents = agents
        self.rollback_enabled = rollback_enabled
        self.checkpoints = []  # State snapshots for rollback
    
    def execute(self, context: OrchestrationContext, **kwargs) -> AgentExecutionResult:
        executed_agents = []
        
        try:
            for agent in self.agents:
                # Create checkpoint before execution
                if self.rollback_enabled:
                    self._create_checkpoint(context)
                
                # Execute agent
                result = agent.execute(context, **kwargs)
                executed_agents.append((agent, result))
                
                if not result.success:
                    self.emit_event('agent_failed', {
                        'agent': agent.name,
                        'error': result.error
                    })
                    raise AgentExecutionError(agent.name, result.error)
            
            return AgentExecutionResult(
                success=True,
                output={'executed_agents': [a.name for a in self.agents]}
            )
        
        except AgentExecutionError as e:
            self.emit_event('orchestration_failed', {'error': str(e)})
            
            if self.rollback_enabled:
                self._rollback_to_last_checkpoint(context)
                self.emit_event('rollback_completed', {
                    'failed_agent': e.agent_name
                })
            
            return AgentExecutionResult(
                success=False,
                output=None,
                error=f"Orchestration failed at {e.agent_name}: {e.error}"
            )
    
    def _create_checkpoint(self, context: OrchestrationContext):
        """Create a snapshot of context state."""
        self.checkpoints.append(context.get_all_data().copy())
    
    def _rollback_to_last_checkpoint(self, context: OrchestrationContext):
        """Restore context to last checkpoint."""
        if self.checkpoints:
            context.data_store = self.checkpoints.pop()

class AgentExecutionError(Exception):
    def __init__(self, agent_name: str, error: str):
        self.agent_name = agent_name
        self.error = error
        super().__init__(f"Agent {agent_name} failed: {error}")
```

### 6.4 Parallel Agent Execution

Execute multiple agents concurrently with dependency tracking.

```python
import asyncio
from typing import List, Tuple

class ParallelOrchestrator(BaseAgent):
    """Executes agents in parallel with dependency resolution."""
    
    def __init__(self, agent_graph: Dict[str, Tuple[BaseAgent, List[str]]]):
        """
        Args:
            agent_graph: Dict mapping agent names to (agent, dependencies) tuples
                Example: {
                    'fraud_detector': (FraudDetectionAgent(), []),
                    'risk_scorer': (RiskScoringAgent(), ['fraud_detector']),
                    'decision_engine': (DecisionEngineAgent(), ['fraud_detector', 'risk_scorer'])
                }
        """
        super().__init__("parallel_orchestrator")
        self.agent_graph = agent_graph
    
    async def execute_async(self, context: OrchestrationContext, **kwargs) -> Dict:
        """Execute agents in topological order respecting dependencies."""
        results = {}
        executed = set()
        
        while len(executed) < len(self.agent_graph):
            # Find agents ready to execute (all dependencies met)
            ready = [
                (name, (agent, deps))
                for name, (agent, deps) in self.agent_graph.items()
                if name not in executed and all(d in executed for d in deps)
            ]
            
            if not ready:
                raise RuntimeError("Circular dependency detected")
            
            # Execute ready agents in parallel
            tasks = [
                agent.execute(context, **kwargs)
                for name, (agent, _) in ready
            ]
            
            for (name, (agent, _)), result in zip(ready, await asyncio.gather(*tasks)):
                results[name] = result
                executed.add(name)
        
        return results

# Usage
agent_graph = {
    'fraud_detector': (FraudDetectionAgent(), []),
    'risk_scorer': (RiskScoringAgent(), ['fraud_detector']),
    'decision_engine': (DecisionEngineAgent(), ['fraud_detector', 'risk_scorer'])
}

orchestrator = ParallelOrchestrator(agent_graph)
results = asyncio.run(orchestrator.execute_async(context, transaction_id='TXN_123'))
```

---

## 7. Real-World Examples

AgentFlow includes complete example applications demonstrating agent composition in different domains:

### 7.1 Healthcare Orchestration

**File:** `examples/healthcare_orchestration.py`

Demonstrates a clinical decision support system with multiple agents:
- **DiagnosisAgent**: Analyzes patient symptoms and history
- **LabResultsAgent**: Processes lab test results
- **RiskAssessmentAgent**: Evaluates patient risk factors
- **TreatmentRecommendationAgent**: Suggests treatment options
- **ComplianceCheckAgent**: Ensures HIPAA compliance

**Key Patterns:**
- Sequential chaining with context sharing
- Error handling for critical healthcare decisions
- Audit trail for compliance
- Rollback capability for safety

### 7.2 E-Commerce Fulfillment

**File:** `examples/ecommerce_fulfillment.py`

Demonstrates an order processing pipeline:
- **OrderValidationAgent**: Validates order data and business rules
- **InventoryAgent**: Checks stock availability
- **PaymentAgent**: Processes payment
- **ShippingAgent**: Arranges fulfillment
- **NotificationAgent**: Sends customer updates

**Key Patterns:**
- Parallel execution of independent agents (inventory + payment checks)
- Conditional routing (different shipping based on location)
- Compensation logic for payment reversal if shipping fails
- Event-driven notifications

### 7.3 FinTech Compliance

**File:** `examples/fintech_compliance.py`

Demonstrates financial regulatory compliance automation:
- **KYCAgent**: Know-Your-Customer verification
- **AMLAgent**: Anti-Money Laundering screening
- **TransactionMonitoringAgent**: Detects suspicious patterns
- **RegulatoryReportingAgent**: Generates compliance reports
- **AuditAgent**: Creates immutable audit trail

**Key Patterns:**
- Complex rule-based validation
- Data integration from multiple sources
- Comprehensive event logging for audits
- Failure handling with escalation

---

## 8. Testing Agents

Unit testing custom agents is essential for reliability. AgentFlow provides testing utilities and patterns.

### 8.1 Mock Context and Testing Utilities

```python
import unittest
from unittest.mock import Mock
from agentflow.context import OrchestrationContext
from agentflow.agents import AgentExecutionResult

class MockOrchestrationContext:
    """Mock context for unit testing agents."""
    
    def __init__(self, initial_data: Dict = None):
        self.data_store = initial_data or {}
        self.event_journal = []
    
    def set_data(self, key: str, value: Any):
        self.data_store[key] = value
    
    def get_data(self, key: str, default: Any = None) -> Any:
        return self.data_store.get(key, default)
    
    def get_all_data(self) -> Dict[str, Any]:
        return self.data_store.copy()
```

### 8.2 Test Example: FraudDetectionAgent

```python
class TestFraudDetectionAgent(unittest.TestCase):
    """Unit tests for FraudDetectionAgent."""
    
    def setUp(self):
        self.agent = FraudDetectionAgent()
        self.context = MockOrchestrationContext()
    
    def test_normal_transaction(self):
        """Test that normal transactions have low fraud score."""
        # Setup: Normal transaction history
        history = {
            'transactions': [
                {'amount': 100},
                {'amount': 120},
                {'amount': 110}
            ]
        }
        self.context.set_data('customer_CUST_001_history', history)
        
        # Execute: Check new transaction of normal amount
        result = self.agent.execute(
            self.context,
            transaction_id='TXN_001',
            customer_id='CUST_001',
            amount=105,
            merchant_category='retail'
        )
        
        # Assert: Low fraud score
        self.assertTrue(result.success)
        self.assertLess(result.output['fraud_score'], 0.3)
        self.assertEqual(result.output['recommendation'], 'allow')
    
    def test_anomalous_transaction(self):
        """Test that anomalous transactions have high fraud score."""
        history = {
            'transactions': [
                {'amount': 100},
                {'amount': 120},
                {'amount': 110}
            ]
        }
        self.context.set_data('customer_CUST_002_history', history)
        
        result = self.agent.execute(
            self.context,
            transaction_id='TXN_002',
            customer_id='CUST_002',
            amount=10000,  # Huge jump from normal
            merchant_category='retail'
        )
        
        self.assertTrue(result.success)
        self.assertGreater(result.output['fraud_score'], 0.5)
    
    def test_missing_parameters(self):
        """Test that missing parameters are handled gracefully."""
        result = self.agent.execute(
            self.context,
            transaction_id='TXN_003'
            # Missing customer_id and amount
        )
        
        self.assertFalse(result.success)
        self.assertIn("Missing required parameters", result.error)
    
    def test_no_customer_history(self):
        """Test behavior when customer has no history."""
        result = self.agent.execute(
            self.context,
            transaction_id='TXN_004',
            customer_id='NEW_CUSTOMER',
            amount=500,
            merchant_category='retail'
        )
        
        self.assertTrue(result.success)
        # New customers get neutral/low fraud score
        self.assertLess(result.output['fraud_score'], 0.3)
    
    def test_high_risk_merchant(self):
        """Test that high-risk merchants increase fraud score."""
        history = {
            'transactions': [{'amount': 100}]
        }
        self.context.set_data('customer_CUST_005_history', history)
        
        result = self.agent.execute(
            self.context,
            transaction_id='TXN_005',
            customer_id='CUST_005',
            amount=100,
            merchant_category='crypto'  # High risk
        )
        
        self.assertTrue(result.success)
        self.assertGreater(result.output['fraud_score'], 0.15)
    
    def test_event_emission(self):
        """Test that agent emits events correctly."""
        history = {'transactions': [{'amount': 100}]}
        self.context.set_data('customer_CUST_006_history', history)
        
        result = self.agent.execute(
            self.context,
            transaction_id='TXN_006',
            customer_id='CUST_006',
            amount=100,
            merchant_category='retail'
        )
        
        self.assertTrue(result.success)
        self.assertEqual(len(self.agent.event_journal), 2)  # started + completed
        self.assertEqual(self.agent.event_journal[0]['type'], 'execution_started')
        self.assertEqual(self.agent.event_journal[1]['type'], 'execution_completed')

if __name__ == '__main__':
    unittest.main()
```

### 8.3 Integration Testing

```python
class TestOrchestrationIntegration(unittest.TestCase):
    """Integration tests for agent coordination."""
    
    def test_fraud_detection_pipeline(self):
        """Test full fraud detection pipeline."""
        context = OrchestrationContext('WF_TEST_001')
        
        # Setup customer data
        context.set_data('customer_CUST_001_history', {
            'transactions': [
                {'amount': 100},
                {'amount': 120},
                {'amount': 110}
            ]
        })
        
        # Execute fraud detector
        fraud_detector = FraudDetectionAgent()
        result1 = fraud_detector.execute(
            context,
            transaction_id='TXN_TEST_001',
            customer_id='CUST_001',
            amount=5000,
            merchant_category='retail'
        )
        
        # Execute risk scorer using fraud detector output
        risk_scorer = RiskScoringAgent()
        result2 = risk_scorer.execute(
            context,
            transaction_id='TXN_TEST_001'
        )
        
        # Verify pipeline
        self.assertTrue(result1.success)
        self.assertTrue(result2.success)
        
        # Verify context sharing
        fraud_score = context.get_data('transaction_TXN_TEST_001_fraud_score')
        self.assertIsNotNone(fraud_score)
        self.assertGreater(fraud_score, 0.5)
```

---

## Summary

Custom agents in AgentFlow follow a consistent pattern:

1. **Inherit** from `BaseAgent`
2. **Implement** the `execute()` method with your business logic
3. **Use** `context.set_data()` and `context.get_data()` for agent communication
4. **Emit** events for observability and auditing
5. **Return** `AgentExecutionResult` with success status and output
6. **Test** with mock contexts and unit tests

AgentFlow's composable agent architecture enables building complex, auditable, and maintainable multi-agent systems. Refer to the example applications for domain-specific patterns and best practices.
