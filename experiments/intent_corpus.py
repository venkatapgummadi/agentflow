"""
A small hand-labelled intent corpus for parser-quality benchmarking.

40 intents across four enterprise verticals (FinTech, HealthTech,
E-Commerce, Insurance), each with a "gold" expected parse:

* ``ops``        -- expected canonical verbs in order (multiset)
* ``entities``   -- expected entity values to be extracted
* ``conditions`` -- expected number of conditional clauses
* ``domain``     -- expected vertical tag

The corpus is intentionally hand-written so we can update gold labels
when the parser changes. It is not meant to be exhaustive; it is a
*sanity baseline* good enough to surface regressions and to compare
the rule-based vs. LLM-backed parser on the same yardstick.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LabelledIntent:
    intent: str
    ops: list[str]
    entities: dict[str, list[str]] = field(default_factory=dict)
    conditions: int = 0
    domain: str = ""
    # Optional: expected numeric thresholds in the intent, when present.
    # Captured separately from ``entities['numeric_id']`` because the rule
    # parser exposes a dedicated ``threshold`` entity type.
    thresholds: list[str] = field(default_factory=list)


CORPUS: list[LabelledIntent] = [
    # ── FinTech ──────────────────────────────────────────────────────
    LabelledIntent(
        "Fetch customer 4421 from CRM and create a loan application if credit score > 700",
        ops=["fetch", "create"], entities={"numeric_id": ["4421"]},
        conditions=2, domain="fintech",
    ),
    LabelledIntent(
        "Get account 9981 balance and transfer 500 to account 1234",
        ops=["get", "transfer"],
        entities={"numeric_id": ["9981", "500", "1234"]}, domain="fintech",
    ),
    LabelledIntent(
        "Validate KYC for member 33112 and notify the underwriting team",
        ops=["validate", "notify"], entities={"numeric_id": ["33112"]},
        domain="fintech",
    ),
    LabelledIntent(
        "Retrieve credit report for 7771 and update risk score to 820",
        ops=["retrieve", "update"], entities={"numeric_id": ["7771", "820"]},
        domain="fintech",
    ),
    LabelledIntent(
        "Cancel pending ACH transaction 55021 and email the customer",
        ops=["cancel", "email"], entities={"numeric_id": ["55021"]},
        domain="fintech",
    ),
    LabelledIntent(
        "Open a high-priority loan application for member 4421 "
        "if credit score is above 720 and notify underwriting",
        ops=["open", "notify"], entities={"numeric_id": ["4421", "720"]},
        conditions=2, domain="fintech",
    ),
    LabelledIntent(
        "Lookup last settlement for account 8800 and reconcile with ledger 99",
        ops=["lookup", "reconcile"],
        entities={"numeric_id": ["8800", "99"]}, domain="fintech",
    ),
    LabelledIntent(
        "Approve loan 12345 if income >= 60000 and DTI < 35",
        ops=["approve"], entities={"numeric_id": ["12345", "60000", "35"]},
        conditions=3, domain="fintech",
    ),
    LabelledIntent(
        "Submit AML alert for transaction 88811 and create a case in the fraud system",
        ops=["submit", "create"], entities={"numeric_id": ["88811"]},
        domain="fintech",
    ),
    LabelledIntent(
        "Fetch wire confirmation for reference 5560 and update the ledger entry",
        ops=["fetch", "update"], entities={"numeric_id": ["5560"]},
        domain="fintech",
    ),
    # ── HealthTech ───────────────────────────────────────────────────
    LabelledIntent(
        "Fetch patient EHR record for member 992 and notify the care team",
        ops=["fetch", "notify"], entities={"numeric_id": ["992"]},
        domain="healthtech",
    ),
    LabelledIntent(
        "Order a contrast CT for member 991 if eGFR > 30",
        ops=["order"], entities={"numeric_id": ["991", "30"]},
        conditions=2, domain="healthtech",
    ),
    LabelledIntent(
        "Retrieve FHIR patient 7711 and create a referral to cardiology",
        ops=["retrieve", "create"], entities={"numeric_id": ["7711"]},
        domain="healthtech",
    ),
    LabelledIntent(
        "Submit prior-authorization request for procedure 27447 and notify provider",
        ops=["submit", "notify"], entities={"numeric_id": ["27447"]},
        domain="healthtech",
    ),
    LabelledIntent(
        "Update allergy list for patient 5520 with peanut allergy",
        ops=["update"], entities={"numeric_id": ["5520"]},
        domain="healthtech",
    ),
    LabelledIntent(
        "Fetch DICOM study 8821 and forward to radiology PACS",
        ops=["fetch", "forward"], entities={"numeric_id": ["8821"]},
        domain="healthtech",
    ),
    LabelledIntent(
        "Verify insurance eligibility for patient 4480 and create an encounter",
        ops=["verify", "create"], entities={"numeric_id": ["4480"]},
        domain="healthtech",
    ),
    LabelledIntent(
        "Cancel appointment 33887 and notify the patient by SMS",
        ops=["cancel", "notify"], entities={"numeric_id": ["33887"]},
        domain="healthtech",
    ),
    LabelledIntent(
        "Order a follow-up lab panel for patient 5012 if HbA1c > 7",
        ops=["order"], entities={"numeric_id": ["5012", "7"]},
        conditions=2, domain="healthtech",
    ),
    LabelledIntent(
        "Submit claim 99021 to payer and update the EHR with the status",
        ops=["submit", "update"], entities={"numeric_id": ["99021"]},
        domain="healthtech",
    ),
    # ── E-Commerce ───────────────────────────────────────────────────
    LabelledIntent(
        "Fetch order 12345 and create a return label",
        ops=["fetch", "create"], entities={"numeric_id": ["12345"]},
        domain="ecommerce",
    ),
    LabelledIntent(
        "Cancel order 99 and refund 200 to the original payment method",
        ops=["cancel", "refund"], entities={"numeric_id": ["99", "200"]},
        domain="ecommerce",
    ),
    LabelledIntent(
        "Update inventory for SKU 4471 to 50 units and notify warehouse 3",
        ops=["update", "notify"],
        entities={"numeric_id": ["4471", "50", "3"]}, domain="ecommerce",
    ),
    LabelledIntent(
        "Lookup customer 9981 cart and apply 10 percent discount if total > 200",
        ops=["lookup", "apply"],
        entities={"numeric_id": ["9981", "10", "200"]},
        conditions=2, domain="ecommerce",
    ),
    LabelledIntent(
        "Create a shipment for order 5550 and update tracking",
        ops=["create", "update"], entities={"numeric_id": ["5550"]},
        domain="ecommerce",
    ),
    LabelledIntent(
        "Fetch SKU 8842 stock level and trigger reorder if below 100",
        ops=["fetch", "trigger"], entities={"numeric_id": ["8842", "100"]},
        conditions=2, domain="ecommerce",
    ),
    LabelledIntent(
        "Apply loyalty 500 points to customer 11223 and email confirmation",
        ops=["apply", "email"],
        entities={"numeric_id": ["500", "11223"]}, domain="ecommerce",
    ),
    LabelledIntent(
        "Get pricing for SKU 7799 and update the catalog",
        ops=["get", "update"], entities={"numeric_id": ["7799"]},
        domain="ecommerce",
    ),
    LabelledIntent(
        "Submit chargeback for order 88811 and notify the customer success team",
        ops=["submit", "notify"], entities={"numeric_id": ["88811"]},
        domain="ecommerce",
    ),
    LabelledIntent(
        "Fetch return 4470 status and refund the customer if approved",
        ops=["fetch", "refund"], entities={"numeric_id": ["4470"]},
        conditions=1, domain="ecommerce",
    ),
    # ── Insurance ────────────────────────────────────────────────────
    LabelledIntent(
        "Fetch policy 33445 and verify coverage for procedure 80021",
        ops=["fetch", "verify"], entities={"numeric_id": ["33445", "80021"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Submit claim for policy 5511 and notify the adjuster",
        ops=["submit", "notify"], entities={"numeric_id": ["5511"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Update beneficiary for policy 7782 to include spouse",
        ops=["update"], entities={"numeric_id": ["7782"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Cancel auto policy 99021 and refund unearned premium",
        ops=["cancel", "refund"], entities={"numeric_id": ["99021"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Approve claim 4400 if loss amount < 5000 and notify the policyholder",
        ops=["approve", "notify"],
        entities={"numeric_id": ["4400", "5000"]},
        conditions=2, domain="insurance",
    ),
    LabelledIntent(
        "Retrieve underwriting decision for policy 11201 and create the binder",
        ops=["retrieve", "create"], entities={"numeric_id": ["11201"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Open a new homeowners policy quote for customer 6630 and email it",
        ops=["open", "email"], entities={"numeric_id": ["6630"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Validate driver record for member 8881 and adjust the premium",
        ops=["validate", "adjust"], entities={"numeric_id": ["8881"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Submit subrogation request for claim 7723 and notify the recovery team",
        ops=["submit", "notify"], entities={"numeric_id": ["7723"]},
        domain="insurance",
    ),
    LabelledIntent(
        "Fetch endorsement 4421 history and update the policy file",
        ops=["fetch", "update"], entities={"numeric_id": ["4421"]},
        domain="insurance",
    ),
]


def by_domain() -> dict[str, list[LabelledIntent]]:
    out: dict[str, list[LabelledIntent]] = {}
    for item in CORPUS:
        out.setdefault(item.domain, []).append(item)
    return out
