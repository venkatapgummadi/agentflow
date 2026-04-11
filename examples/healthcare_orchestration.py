"""
Example: Healthcare API Orchestration with HIPAA-Compliant Data Flow.

Demonstrates how AgentFlow orchestrates a patient referral workflow
across multiple healthcare systems (EHR, lab, pharmacy, insurance)
with audit logging suitable for HIPAA compliance.

Real-world scenario:
  A patient needs a specialist referral. This requires:
  1. Fetching patient demographics from the EHR (Epic/Cerner)
  2. Retrieving recent lab results (HL7 FHIR)
  3. Checking insurance eligibility and prior authorization
  4. Submitting the referral order
  5. Notifying the patient and specialist via secure messaging

Author: Venkata Pavan Kumar Gummadi
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from agentflow import AgentOrchestrator, ExecutionPlan, PlanStep
from agentflow.agents.base_agent import BaseAgent
from agentflow.connectors.base import APIEndpoint, APIResponse, BaseConnector
from agentflow.core.context import EventType, OrchestrationContext
from agentflow.core.plan import StepType
from agentflow.routing.dynamic_router import DynamicRouter, RoutingWeights


# ── Healthcare-Specific Connectors ──────────────────────────────────────


class FHIRConnector(BaseConnector):
    """
    HL7 FHIR R4 API connector for Electronic Health Records.

    Connects to FHIR-compliant EHR systems (Epic, Cerner, Allscripts)
    for patient data exchange following healthcare interoperability
    standards.
    """

    def __init__(self, base_url: str, tenant_id: str = "", **kwargs):
        super().__init__(name="FHIR-EHR", config={"base_url": base_url, "tenant_id": tenant_id})
        self.base_url = base_url
        self.tenant_id = tenant_id
        self._register_fhir_endpoints()

    def _register_fhir_endpoints(self):
        """Register standard FHIR R4 resource endpoints."""
        fhir_resources = [
            (
                "Patient",
                "GET",
                "/Patient/{id}",
                "Retrieve patient demographics",
                ["patient", "demographics", "ehr"],
            ),
            (
                "Observation",
                "GET",
                "/Observation?patient={id}",
                "Fetch lab results and vitals",
                ["labs", "vitals", "observation"],
            ),
            (
                "Condition",
                "GET",
                "/Condition?patient={id}",
                "Get active diagnoses",
                ["diagnosis", "condition", "clinical"],
            ),
            (
                "MedicationRequest",
                "GET",
                "/MedicationRequest?patient={id}",
                "Active prescriptions",
                ["medication", "pharmacy", "rx"],
            ),
            (
                "ServiceRequest",
                "POST",
                "/ServiceRequest",
                "Create referral order",
                ["referral", "order", "specialist"],
            ),
            (
                "Coverage",
                "GET",
                "/Coverage?beneficiary={id}",
                "Insurance coverage details",
                ["insurance", "coverage", "eligibility"],
            ),
            (
                "Communication",
                "POST",
                "/Communication",
                "Send secure message",
                ["messaging", "notification", "hipaa"],
            ),
        ]

        for name, method, path, desc, tags in fhir_resources:
            self.register_endpoint(APIEndpoint(
                name=f"FHIR {name}",
                method=method,
                path=path,
                description=desc,
                tags=tags,
                latency_p95_ms=120,
                cost_per_call=0.002,
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
        """Execute a FHIR API call with HIPAA audit headers."""
        params = parameters or {}
        patient_id = params.get("patient_id", "unknown")

        # Simulated FHIR responses for each resource type
        mock_responses = {
            "Patient": {
                "resourceType": "Patient",
                "id": patient_id,
                "name": [{"family": "Smith", "given": ["John"]}],
                "birthDate": "1985-03-15",
                "gender": "male",
                "address": [{"city": "Austin", "state": "TX"}],
            },
            "Observation": {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "code": {"text": "HbA1c"},
                            "valueQuantity": {"value": 6.2, "unit": "%"},
                        }
                    },
                    {
                        "resource": {
                            "code": {"text": "LDL Cholesterol"},
                            "valueQuantity": {"value": 128, "unit": "mg/dL"},
                        }
                    },
                    {
                        "resource": {
                            "code": {"text": "Blood Pressure"},
                            "valueString": "132/85 mmHg",
                        }
                    },
                ],
            },
            "Coverage": {
                "resourceType": "Coverage",
                "status": "active",
                "payor": [{"display": "Blue Cross Blue Shield"}],
                "class": [
                    {"type": {"text": "plan"}, "value": "PPO Gold"}
                ],
                "period": {"start": "2026-01-01", "end": "2026-12-31"},
            },
            "ServiceRequest": {
                "resourceType": "ServiceRequest",
                "id": "ref-20260411-001",
                "status": "active",
                "intent": "order",
                "code": {"text": "Cardiology Consultation"},
                "authoredOn": "2026-04-11",
            },  # noqa: E501
            "Communication": {
                "resourceType": "Communication",
                "status": "completed",
                "sent": "2026-04-11T10:30:00Z",
            },
        }

        # Match operation to FHIR resource
        resource_type = "Patient"
        for rt in mock_responses:
            if rt.lower() in operation.lower():
                resource_type = rt
                break

        return APIResponse(
            status_code=200,
            body=mock_responses.get(resource_type, {}),
            headers={
                "X-FHIR-Audit": f"patient={patient_id}",
                "X-Request-Id": "fhir-req-001",
            },
            latency_ms=85,
            connector_id=self.connector_id,
        )

    async def health_check(self) -> bool:
        return True


class InsuranceConnector(BaseConnector):
    """
    Insurance eligibility and prior authorization connector.

    Integrates with payer systems for real-time eligibility verification
    (X12 270/271) and prior authorization (X12 278).
    """

    def __init__(self, payer_url: str = "", **kwargs):
        super().__init__(
            name="Insurance-Gateway", config={"payer_url": payer_url}
        )
        self.register_endpoint(APIEndpoint(
            name="Eligibility Check",
            method="POST",
            path="/eligibility/verify",
            description=(
                "Real-time insurance eligibility verification (X12 270/271)"
            ),
            tags=["insurance", "eligibility", "x12"],
            latency_p95_ms=200,
            cost_per_call=0.05,
            rate_limit_rpm=200,
        ))
        self.register_endpoint(APIEndpoint(
            name="Prior Authorization",
            method="POST",
            path="/auth/prior",
            description="Submit prior authorization request (X12 278)",
            tags=["insurance", "authorization", "referral"],
            latency_p95_ms=500,
            cost_per_call=0.10,
            rate_limit_rpm=100,
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
        if "auth" in operation.lower():
            return APIResponse(status_code=200, body={
                "authorization_number": "PA-2026-04-78901",
                "status": "approved",
                "valid_through": "2026-07-11",
                "approved_visits": 3,
            }, connector_id=self.connector_id, latency_ms=320)
        else:
            return APIResponse(status_code=200, body={
                "eligible": True,
                "plan": "PPO Gold",
                "copay": 40,
                "specialist_copay": 75,
                "deductible_remaining": 1200,
            }, connector_id=self.connector_id, latency_ms=150)

    async def health_check(self) -> bool:
        return True


# ── Healthcare-Specific Agent ───────────────────────────────────────────


class ClinicalDecisionAgent(BaseAgent):
    """
    Custom agent that applies clinical decision rules to orchestration.

    Checks whether a referral is clinically indicated based on
    patient lab values and conditions before proceeding with the
    authorization and order submission steps.
    """

    def __init__(self):
        super().__init__(name="ClinicalDecisionAgent")
        self.rules = {
            "cardiology_referral": {
                "conditions": ["elevated_bp", "high_ldl", "diabetes_risk"],
                "thresholds": {
                    "systolic_bp": 130,
                    "ldl": 100,
                    "hba1c": 6.0,
                },
            },
        }

    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> Dict[str, Any]:
        lab_results = kwargs.get("lab_results", {})
        referral_type = kwargs.get("referral_type", "cardiology_referral")

        self.emit_event(
            context, EventType.AGENT_MESSAGE,
            message=f"Evaluating clinical rules for {referral_type}",
        )

        decision = self._evaluate_rules(lab_results, referral_type)

        self.emit_event(
            context,
            EventType.VALIDATION_PASSED if decision["recommended"] else EventType.VALIDATION_FAILED,
            message=f"Clinical decision: {'RECOMMENDED' if decision['recommended'] else 'NOT INDICATED'}",
            payload=decision,
        )

        return decision

    def _evaluate_rules(self, lab_results: Dict, referral_type: str) -> Dict[str, Any]:
        rules = self.rules.get(referral_type, {})
        thresholds = rules.get("thresholds", {})
        findings = []

        labs = lab_results.get("entry", []) if isinstance(lab_results, dict) else []

        for entry in labs:
            resource = entry.get("resource", {})
            code = resource.get("code", {}).get("text", "")
            value = resource.get("valueQuantity", {}).get("value")

            if "HbA1c" in code and value and value > thresholds.get("hba1c", 999):
                findings.append(f"Elevated HbA1c: {value}% (threshold: {thresholds['hba1c']}%)")
            elif "LDL" in code and value and value > thresholds.get("ldl", 999):
                findings.append(f"Elevated LDL: {value} mg/dL (threshold: {thresholds['ldl']} mg/dL)")
            elif "Blood Pressure" in code:
                bp_str = resource.get("valueString", "")
                try:
                    systolic = int(bp_str.split("/")[0])
                    if systolic > thresholds.get("systolic_bp", 999):
                        findings.append(f"Elevated systolic BP: {systolic} mmHg (threshold: {thresholds['systolic_bp']})")
                except (ValueError, IndexError):
                    pass

        return {
            "recommended": len(findings) >= 2,
            "findings": findings,
            "finding_count": len(findings),
            "referral_type": referral_type,
            "clinical_summary": (
                f"{len(findings)} clinical indicators support referral"
                if findings
                else "Insufficient clinical indicators for referral"
            ),
        }


# ── Main Orchestration ──────────────────────────────────────────────────


async def run_patient_referral_workflow():
    """
    Execute a complete patient referral workflow.

    Scenario: Dr. Rodriguez orders a cardiology referral for patient
    John Smith based on elevated cardiovascular risk markers.
    """
    print("=" * 70)
    print("  HEALTHCARE API ORCHESTRATION — Patient Referral Workflow")
    print("=" * 70)

    # 1. Initialize connectors
    fhir = FHIRConnector(base_url="https://ehr.hospital.org/fhir/r4", tenant_id="hosp-001")
    insurance = InsuranceConnector(payer_url="https://payer-gateway.bcbs.com")

    # 2. Configure orchestrator with healthcare-appropriate routing
    # Prioritize reliability over cost for healthcare
    router = DynamicRouter(weights=RoutingWeights.high_availability())
    orchestrator = AgentOrchestrator(connectors=[fhir, insurance], router=router)

    patient_id = "patient-12345"
    print(f"\nPatient ID: {patient_id}")
    print(f"Referring Physician: Dr. Rodriguez")
    print(f"Referral Type: Cardiology Consultation")
    print("-" * 70)

    # 3. Step-by-step orchestration with clinical decision support

    # Phase 1: Gather patient data (parallel)
    print("\n[Phase 1] Gathering patient data (parallel)...")
    context = OrchestrationContext(intent="Patient referral for cardiology")

    demographics = await fhir.invoke("Patient", parameters={"patient_id": patient_id})
    labs = await fhir.invoke("Observation", parameters={"patient_id": patient_id})
    coverage = await fhir.invoke("Coverage", parameters={"patient_id": patient_id})

    print(f"  Patient: {demographics.body['name'][0]['given'][0]} {demographics.body['name'][0]['family']}")
    print(f"  DOB: {demographics.body['birthDate']}")
    print(f"  Lab results: {len(labs.body['entry'])} observations")
    print(f"  Insurance: {coverage.body['payor'][0]['display']} ({coverage.body['class'][0]['value']})")

    # Phase 2: Clinical decision support
    print("\n[Phase 2] Clinical decision evaluation...")
    clinical_agent = ClinicalDecisionAgent()
    decision = await clinical_agent.execute(
        context,
        lab_results=labs.body,
        referral_type="cardiology_referral",
    )

    print(f"  Recommendation: {'PROCEED' if decision['recommended'] else 'NOT INDICATED'}")
    for finding in decision["findings"]:
        print(f"    - {finding}")

    if not decision["recommended"]:
        print("\n  Referral not clinically indicated. Workflow stopped.")
        return

    # Phase 3: Insurance verification
    print("\n[Phase 3] Insurance eligibility and prior authorization...")
    eligibility = await insurance.invoke("eligibility/verify", parameters={"patient_id": patient_id})
    print(f"  Eligible: {eligibility.body['eligible']}")
    print(f"  Specialist copay: ${eligibility.body['specialist_copay']}")
    print(f"  Deductible remaining: ${eligibility.body['deductible_remaining']}")

    if eligibility.body["eligible"]:
        auth = await insurance.invoke("auth/prior", parameters={
            "patient_id": patient_id,
            "referral_type": "cardiology",
            "diagnosis_codes": ["I10", "E78.5"],
        })
        print(f"  Authorization: {auth.body['status'].upper()}")
        print(f"  Auth number: {auth.body['authorization_number']}")
        print(f"  Approved visits: {auth.body['approved_visits']}")

    # Phase 4: Submit referral order
    print("\n[Phase 4] Submitting referral order...")
    referral = await fhir.invoke("ServiceRequest", parameters={
        "patient_id": patient_id,
        "specialty": "cardiology",
        "reason": decision["clinical_summary"],
        "authorization": auth.body["authorization_number"],
    })
    print(f"  Referral ID: {referral.body['id']}")
    print(f"  Status: {referral.body['status']}")

    # Phase 5: Notifications
    print("\n[Phase 5] Sending secure notifications...")
    notification = await fhir.invoke("Communication", parameters={
        "patient_id": patient_id,
        "message": "Your cardiology referral has been approved.",
    })
    print(f"  Patient notification: {notification.body['status']}")

    # Audit trail
    print("\n" + "=" * 70)
    print("  HIPAA AUDIT TRAIL")
    print("=" * 70)
    for event in context.journal:
        print(f"  [{event.event_type.value:25s}] {event.message}")

    print(f"\n  Total audit events: {len(context.journal)}")
    print(f"  Orchestration duration: {context.duration:.2f}s")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_patient_referral_workflow())
