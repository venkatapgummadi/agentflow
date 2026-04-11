"""
Example: Building Custom Agents with AgentFlow.

Shows how to create specialized agents that extend the framework
for domain-specific orchestration logic.

Author: Venkata Pavan Kumar Gummadi
"""

import asyncio
from typing import Any, Dict

from agentflow.agents.base_agent import BaseAgent
from agentflow.core.context import EventType, OrchestrationContext
from agentflow.core.plan import ExecutionPlan, PlanStep, StepType


class CreditScoringAgent(BaseAgent):
    """
    Custom agent that enriches customer data with credit scoring.

    Demonstrates how to build domain-specific agents that plug into
    the AgentFlow orchestration pipeline.
    """

    def __init__(self, scoring_model: str = "fico_v9"):
        super().__init__(name="CreditScoringAgent")
        self.scoring_model = scoring_model

    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> Dict[str, Any]:
        customer_data = kwargs.get("customer_data", {})

        self.emit_event(
            context,
            EventType.AGENT_MESSAGE,
            message=f"Scoring customer with model {self.scoring_model}",
        )

        # Domain-specific credit scoring logic
        score = self._calculate_score(customer_data)

        await context.set(self.agent_id, "credit_score", score)

        self.emit_event(
            context,
            EventType.STEP_COMPLETED,
            message=f"Credit score calculated: {score['score']}",
        )

        return score

    def _calculate_score(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate credit score based on customer financial data.

        In production, this would call a credit bureau API or
        run an ML model.
        """
        income = customer_data.get("annual_income", 0)
        debt = customer_data.get("total_debt", 0)
        history_years = customer_data.get("credit_history_years", 0)

        # Simplified scoring model
        base_score = 300
        income_factor = min(income / 100000, 2.0) * 150
        debt_ratio = debt / max(income, 1)
        debt_penalty = max(0, debt_ratio - 0.3) * 200
        history_bonus = min(history_years, 20) * 10

        score = int(base_score + income_factor - debt_penalty + history_bonus)
        score = max(300, min(850, score))

        return {
            "score": score,
            "model": self.scoring_model,
            "factors": {
                "income_factor": round(income_factor, 1),
                "debt_penalty": round(debt_penalty, 1),
                "history_bonus": round(history_bonus, 1),
            },
            "recommendation": (
                "approve" if score >= 700 else "review"
                if score >= 600 else "decline"
            ),
        }


class FraudDetectionAgent(BaseAgent):
    """
    Custom agent for real-time fraud detection on API transactions.

    Analyzes orchestration patterns and step results for anomalies.
    """

    def __init__(self, risk_threshold: float = 0.7):
        super().__init__(name="FraudDetectionAgent")
        self.risk_threshold = risk_threshold

    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> Dict[str, Any]:
        transaction_data = kwargs.get("transaction_data", {})

        risk_score = self._assess_risk(transaction_data)
        flagged = risk_score > self.risk_threshold

        if flagged:
            self.emit_event(
                context,
                EventType.VALIDATION_FAILED,
                message=f"Fraud risk detected: score={risk_score:.2f}",
                payload={"risk_score": risk_score},
            )

        return {
            "risk_score": round(risk_score, 3),
            "flagged": flagged,
            "action": "block" if flagged else "allow",
        }

    def _assess_risk(self, data: Dict[str, Any]) -> float:
        """Simplified risk scoring — production uses ML model."""
        score = 0.0
        if data.get("amount", 0) > 10000:
            score += 0.3
        if data.get("country") != data.get("customer_country"):
            score += 0.4
        if data.get("time_since_last_transaction", 999) < 60:
            score += 0.2
        return min(score, 1.0)


async def main():
    context = OrchestrationContext(intent="Process loan application")

    # Use custom credit scoring agent
    scorer = CreditScoringAgent(scoring_model="fico_v9")
    score_result = await scorer.execute(
        context,
        customer_data={
            "annual_income": 85000,
            "total_debt": 15000,
            "credit_history_years": 8,
        },
    )
    print(f"Credit Score: {score_result['score']}")
    print(f"Recommendation: {score_result['recommendation']}")

    # Use custom fraud detection agent
    fraud_agent = FraudDetectionAgent(risk_threshold=0.5)
    fraud_result = await fraud_agent.execute(
        context,
        transaction_data={
            "amount": 25000,
            "country": "US",
            "customer_country": "US",
            "time_since_last_transaction": 3600,
        },
    )
    print(f"\nFraud Risk: {fraud_result['risk_score']}")
    print(f"Action: {fraud_result['action']}")

    # Inspect audit trail
    print(f"\nAudit events: {len(context.journal)}")
    for event in context.journal:
        print(f"  [{event.event_type.value}] {event.message}")


if __name__ == "__main__":
    asyncio.run(main())
