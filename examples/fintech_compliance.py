"""
Example: FinTech Payment Processing with Regulatory Compliance.

Demonstrates AgentFlow orchestrating a cross-border payment workflow
that coordinates KYC verification, sanctions screening, fraud detection,
currency conversion, and regulatory reporting across multiple APIs.

Real-world scenario:
  A FinTech company processes an international wire transfer. The workflow must:
  1. Verify sender and receiver KYC status
  2. Screen both parties against OFAC/EU sanctions lists
  3. Run real-time fraud scoring
  4. Convert currency at live rates
  5. Execute the payment through SWIFT/banking APIs
  6. File regulatory reports (SAR if triggered, CTR for large amounts)

Author: Venkata Pavan Kumar Gummadi
"""

import asyncio
import uuid
from typing import Any

from agentflow.agents.base_agent import BaseAgent
from agentflow.connectors.base import APIEndpoint, APIResponse, BaseConnector
from agentflow.core.context import EventType, OrchestrationContext

# ── FinTech Connectors ──────────────────────────────────────────────────


class KYCConnector(BaseConnector):
    """Know Your Customer verification connector."""

    def __init__(self):
        super().__init__(name="KYC-Service")
        self.register_endpoint(
            APIEndpoint(
                name="KYC Verify",
                method="POST",
                path="/kyc/verify",
                description="Verify customer identity and KYC status",
                tags=["kyc", "identity", "compliance"],
                latency_p95_ms=400,
                cost_per_call=0.50,
                rate_limit_rpm=200,
            )
        )

    def discover(self) -> list[dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        params = parameters or {}
        customer_id = params.get("customer_id", "")
        return APIResponse(
            status_code=200,
            body={
                "customer_id": customer_id,
                "kyc_status": "verified",
                "verification_level": "enhanced",
                "risk_rating": "medium",
                "last_verified": "2026-03-15",
                "document_types": ["passport", "utility_bill"],
                "pep_status": False,
            },
            connector_id=self.connector_id,
            latency_ms=280,
        )

    async def health_check(self) -> bool:
        return True


class SanctionsConnector(BaseConnector):
    """OFAC, EU, and UN sanctions screening connector."""

    def __init__(self):
        super().__init__(name="Sanctions-Screening")
        self.register_endpoint(
            APIEndpoint(
                name="Sanctions Screen",
                method="POST",
                path="/sanctions/screen",
                description="Screen against OFAC, EU, UN sanctions lists",
                tags=["sanctions", "ofac", "compliance", "aml"],
                latency_p95_ms=600,
                cost_per_call=0.25,
                rate_limit_rpm=300,
            )
        )

    def discover(self) -> list[dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        params = parameters or {}
        return APIResponse(
            status_code=200,
            body={
                "screened_name": params.get("name", ""),
                "match_found": False,
                "lists_checked": ["OFAC SDN", "EU Consolidated", "UN Security Council"],
                "confidence": 0.0,
                "screening_id": f"SCR-{uuid.uuid4().hex[:8]}",
                "timestamp": "2026-04-11T10:00:00Z",
            },
            connector_id=self.connector_id,
            latency_ms=450,
        )

    async def health_check(self) -> bool:
        return True


class FXConnector(BaseConnector):
    """Foreign exchange rate and conversion connector."""

    def __init__(self):
        super().__init__(name="FX-Service")
        self._rates = {
            ("USD", "EUR"): 0.92,
            ("USD", "GBP"): 0.79,
            ("USD", "JPY"): 149.50,
            ("EUR", "USD"): 1.09,
            ("GBP", "USD"): 1.27,
            ("JPY", "USD"): 0.0067,
            ("EUR", "GBP"): 0.86,
            ("GBP", "EUR"): 1.16,
        }
        self.register_endpoint(
            APIEndpoint(
                name="FX Convert",
                method="POST",
                path="/fx/convert",
                description="Real-time currency conversion",
                tags=["fx", "currency", "conversion"],
                latency_p95_ms=80,
                cost_per_call=0.01,
                rate_limit_rpm=1000,
            )
        )

    def discover(self) -> list[dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        params = parameters or {}
        from_curr = params.get("from_currency", "USD")
        to_curr = params.get("to_currency", "EUR")
        amount = params.get("amount", 0)
        rate = self._rates.get((from_curr, to_curr), 1.0)
        converted = round(amount * rate, 2)

        return APIResponse(
            status_code=200,
            body={
                "from": {"currency": from_curr, "amount": amount},
                "to": {"currency": to_curr, "amount": converted},
                "rate": rate,
                "rate_timestamp": "2026-04-11T10:00:01Z",
                "quote_id": f"FXQ-{uuid.uuid4().hex[:8]}",
                "valid_for_seconds": 30,
            },
            connector_id=self.connector_id,
            latency_ms=45,
        )

    async def health_check(self) -> bool:
        return True


class PaymentRailConnector(BaseConnector):
    """SWIFT and domestic payment rail connector."""

    def __init__(self):
        super().__init__(name="Payment-Rail")
        self.register_endpoint(
            APIEndpoint(
                name="SWIFT Transfer",
                method="POST",
                path="/transfer/swift",
                description="Execute international SWIFT wire transfer",
                tags=["swift", "wire", "international", "payment"],
                latency_p95_ms=2000,
                cost_per_call=15.00,
                rate_limit_rpm=50,
            )
        )

    def discover(self) -> list[dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        return APIResponse(
            status_code=200,
            body={
                "transfer_id": f"SWF-{uuid.uuid4().hex[:10].upper()}",
                "status": "processing",
                "swift_reference": f"SWIFT{uuid.uuid4().hex[:12].upper()}",
                "estimated_settlement": "2026-04-13",
                "fees": {"sending_bank": 25.00, "correspondent": 15.00, "receiving_bank": 10.00},
                "total_fees": 50.00,
            },
            connector_id=self.connector_id,
            latency_ms=1800,
        )

    async def health_check(self) -> bool:
        return True


# ── Compliance Agent ────────────────────────────────────────────────────


class ComplianceAgent(BaseAgent):
    """
    Regulatory compliance agent for financial transactions.

    Evaluates whether a transaction requires:
    - Suspicious Activity Report (SAR) filing
    - Currency Transaction Report (CTR) for amounts > $10,000
    - Enhanced due diligence for high-risk jurisdictions
    """

    HIGH_RISK_COUNTRIES = {"IR", "KP", "SY", "CU", "VE"}
    CTR_THRESHOLD = 10000.00  # USD

    def __init__(self):
        super().__init__(name="ComplianceAgent")

    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> dict[str, Any]:
        transaction = kwargs.get("transaction", {})
        kyc_sender = kwargs.get("kyc_sender", {})
        kyc_receiver = kwargs.get("kyc_receiver", {})
        sanctions_result = kwargs.get("sanctions_result", {})
        fraud_score = kwargs.get("fraud_score", 0.0)

        self.emit_event(
            context,
            EventType.AGENT_MESSAGE,
            message="Evaluating regulatory compliance",
        )

        findings = []
        actions_required = []
        risk_level = "low"

        # CTR check
        amount_usd = transaction.get("amount_usd", 0)
        if amount_usd >= self.CTR_THRESHOLD:
            findings.append(
                f"Amount ${amount_usd:,.2f} exceeds CTR threshold (${self.CTR_THRESHOLD:,.2f})"
            )
            actions_required.append("FILE_CTR")
            risk_level = "medium"

        # Sanctions match
        if sanctions_result.get("match_found"):
            findings.append("Sanctions match detected")
            actions_required.append("BLOCK_TRANSACTION")
            actions_required.append("FILE_SAR")
            risk_level = "critical"

        # High-risk jurisdiction
        receiver_country = transaction.get("receiver_country", "")
        if receiver_country in self.HIGH_RISK_COUNTRIES:
            findings.append(f"High-risk jurisdiction: {receiver_country}")
            actions_required.append("ENHANCED_DUE_DILIGENCE")
            risk_level = "high"

        # Fraud score
        if fraud_score > 0.7:
            findings.append(f"Elevated fraud score: {fraud_score}")
            actions_required.append("MANUAL_REVIEW")
            actions_required.append("FILE_SAR")
            risk_level = "high"

        # PEP check
        if kyc_sender.get("pep_status") or kyc_receiver.get("pep_status"):
            findings.append("Politically Exposed Person involved")
            actions_required.append("ENHANCED_DUE_DILIGENCE")
            if risk_level == "low":
                risk_level = "medium"

        approved = "BLOCK_TRANSACTION" not in actions_required

        self.emit_event(
            context,
            (EventType.VALIDATION_PASSED if approved else EventType.VALIDATION_FAILED),
            message=(
                f"Compliance decision: {'APPROVED' if approved else 'BLOCKED'} (risk: {risk_level})"
            ),
            payload={"risk_level": risk_level, "actions": actions_required},
        )

        return {
            "approved": approved,
            "risk_level": risk_level,
            "findings": findings,
            "actions_required": actions_required,
            "compliance_id": f"CMP-{uuid.uuid4().hex[:8]}",
        }


# ── Main Orchestration ──────────────────────────────────────────────────


async def main():
    print("=" * 70)
    print("  FINTECH CROSS-BORDER PAYMENT — Compliance Orchestration")
    print("=" * 70)

    # Transaction details
    transaction = {
        "sender_id": "CUST-US-001",
        "sender_name": "Acme Corp",
        "sender_country": "US",
        "receiver_id": "CUST-DE-042",
        "receiver_name": "Berlin GmbH",
        "receiver_country": "DE",
        "amount": 25000.00,
        "currency": "USD",
        "target_currency": "EUR",
        "amount_usd": 25000.00,
        "purpose": "Invoice payment - Q1 consulting services",
    }

    print(f"\nTransaction: {transaction['sender_name']} -> {transaction['receiver_name']}")
    amount = transaction["amount"]
    currency = transaction["currency"]
    target_currency = transaction["target_currency"]
    print(f"Amount: ${amount:,.2f} {currency} -> {target_currency}")
    sender_country = transaction["sender_country"]
    receiver_country = transaction["receiver_country"]
    print(f"Route: {sender_country} -> {receiver_country}")
    print("-" * 70)

    # Initialize connectors
    kyc = KYCConnector()
    sanctions = SanctionsConnector()
    fx = FXConnector()
    payment_rail = PaymentRailConnector()

    context = OrchestrationContext(intent="Cross-border wire transfer with compliance")

    # Phase 1: KYC verification (parallel for sender and receiver)
    print("\n[Phase 1] KYC Verification (parallel)...")
    kyc_sender, kyc_receiver = await asyncio.gather(
        kyc.invoke(
            "verify",
            parameters={
                "customer_id": transaction["sender_id"],
                "name": transaction["sender_name"],
            },
        ),
        kyc.invoke(
            "verify",
            parameters={
                "customer_id": transaction["receiver_id"],
                "name": transaction["receiver_name"],
            },
        ),
    )
    sender_status = kyc_sender.body["kyc_status"]
    sender_risk = kyc_sender.body["risk_rating"]
    print(f"  Sender KYC: {sender_status} (risk: {sender_risk})")
    receiver_status = kyc_receiver.body["kyc_status"]
    receiver_risk = kyc_receiver.body["risk_rating"]
    print(f"  Receiver KYC: {receiver_status} (risk: {receiver_risk})")

    # Phase 2: Sanctions screening (parallel)
    print("\n[Phase 2] Sanctions Screening (parallel)...")
    sanc_sender, sanc_receiver = await asyncio.gather(
        sanctions.invoke(
            "screen",
            parameters={
                "name": transaction["sender_name"],
                "country": transaction["sender_country"],
            },
        ),
        sanctions.invoke(
            "screen",
            parameters={
                "name": transaction["receiver_name"],
                "country": transaction["receiver_country"],
            },
        ),
    )
    print(f"  Sender: {'CLEAR' if not sanc_sender.body['match_found'] else 'MATCH FOUND'}")
    print(f"  Receiver: {'CLEAR' if not sanc_receiver.body['match_found'] else 'MATCH FOUND'}")
    lists_checked = ", ".join(sanc_sender.body["lists_checked"])
    print(f"  Lists checked: {lists_checked}")

    # Phase 3: Compliance evaluation
    print("\n[Phase 3] Regulatory Compliance Evaluation...")
    compliance_agent = ComplianceAgent()
    compliance = await compliance_agent.execute(
        context,
        transaction=transaction,
        kyc_sender=kyc_sender.body,
        kyc_receiver=kyc_receiver.body,
        sanctions_result=sanc_sender.body,
        fraud_score=0.12,
    )
    decision = "APPROVED" if compliance["approved"] else "BLOCKED"
    print(f"  Decision: {decision}")
    risk_level = compliance["risk_level"].upper()
    print(f"  Risk level: {risk_level}")
    for finding in compliance["findings"]:
        print(f"    - {finding}")
    for action in compliance["actions_required"]:
        print(f"    Action: {action}")

    if not compliance["approved"]:
        print("\n  Transaction BLOCKED. Workflow terminated.")
        return

    # Phase 4: Currency conversion
    print("\n[Phase 4] Currency Conversion...")
    fx_result = await fx.invoke(
        "convert",
        parameters={
            "from_currency": transaction["currency"],
            "to_currency": transaction["target_currency"],
            "amount": transaction["amount"],
        },
    )
    fx_body = fx_result.body
    from_curr = fx_body["from"]["currency"]
    to_curr = fx_body["to"]["currency"]
    rate = fx_body["rate"]
    print(f"  Rate: 1 {from_curr} = {rate} {to_curr}")
    amount_converted = fx_body["to"]["amount"]
    print(f"  Converted: {to_curr} {amount_converted:,.2f}")
    valid_seconds = fx_body["valid_for_seconds"]
    print(f"  Quote valid for: {valid_seconds}s")

    # Phase 5: Execute SWIFT transfer
    print("\n[Phase 5] Executing SWIFT Transfer...")
    transfer = await payment_rail.invoke(
        "transfer/swift",
        parameters={
            "sender": transaction["sender_id"],
            "receiver": transaction["receiver_id"],
            "amount": fx_body["to"]["amount"],
            "currency": transaction["target_currency"],
            "fx_quote_id": fx_body["quote_id"],
            "compliance_id": compliance["compliance_id"],
        },
    )
    t = transfer.body
    print(f"  Transfer ID: {t['transfer_id']}")
    print(f"  SWIFT Ref: {t['swift_reference']}")
    print(f"  Status: {t['status'].upper()}")
    print(f"  Settlement: {t['estimated_settlement']}")
    sending_fee = t["fees"]["sending_bank"]
    correspondent_fee = t["fees"]["correspondent"]
    receiving_fee = t["fees"]["receiving_bank"]
    total_fees = t["total_fees"]
    print(
        f"  Fees: ${total_fees:.2f} (sending: ${sending_fee}, "
        f"correspondent: ${correspondent_fee}, receiving: ${receiving_fee})"
    )

    # Summary
    print(f"\n{'=' * 70}")
    print("  TRANSACTION SUMMARY")
    print(f"{'=' * 70}")
    sent_amount = transaction["amount"]
    print(f"  Sent: ${sent_amount:,.2f} USD")
    received_currency = fx_body["to"]["currency"]
    received_amount = fx_body["to"]["amount"]
    print(f"  Received: {received_currency} {received_amount:,.2f}")
    print(f"  Total fees: ${t['total_fees']:.2f}")
    risk_level = compliance["risk_level"].upper()
    compliance_id = compliance["compliance_id"]
    print(f"  Compliance: {risk_level} risk | {compliance_id}")
    print(f"  Audit events: {len(context.journal)}")
    print(f"  Duration: {context.duration:.3f}s")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
