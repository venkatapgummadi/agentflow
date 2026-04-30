"""
Intent Parser — natural language to structured API workflow.

Parses natural-language descriptions of API workflows into structured
operations that the PlannerAgent can convert to execution plans.

Supports:
- Entity extraction (API names, parameters, conditions)
- Operation decomposition (multi-step workflows)
- Conditional logic detection ("if X then Y")
- Aggregation patterns ("combine", "merge", "join")

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Operation Patterns ──────────────────────────────────────────────────

OPERATION_PATTERNS: dict[str, list[str]] = {
    "api_call": [
        # read-side verbs
        r"\b(fetch|get|retrieve|lookup|read|find|search|query)\b",
        # creation / open
        r"\b(create|post|add|insert|register|submit|open)\b",
        # mutation
        r"\b(update|put|patch|modify|change|set|adjust)\b",
        # deletion / cancellation
        r"\b(delete|remove|destroy|drop|cancel)\b",
        # decision verbs (common in enterprise workflows)
        r"\b(approve|reject|deny|sign|authorize)\b",
        # money / order verbs
        r"\b(transfer|refund|charge|invoice|reorder|order)\b",
        # validation verbs
        r"\b(validate|verify|check|audit|confirm|reconcile)\b",
        # notification verbs
        r"\b(notify|alert|email|page|sms|message|announce)\b",
        # workflow verbs
        r"\b(trigger|apply|forward|route|escalate|dispatch)\b",
        # lifecycle verbs
        r"\b(enable|disable|activate|deactivate|suspend|resume|archive|restore)\b",
    ],
    "transform": [
        r"\b(enrich|augment|enhance|supplement|append)\b",
        r"\b(transform|convert|map|reshape|format)\b",
        r"\b(extract|parse|filter|select)\b",
    ],
    "condition": [
        r"\b(if|when|unless|provided|given)\b.*\b(then|do|execute)\b",
        r"\b(check|verify|validate|ensure|confirm)\b.*\b(before|prior)\b",
        r"\bif\b.+\b(greater|less|equal|above|below|more|fewer)\b",
    ],
    "aggregate": [
        r"\b(combine|merge|join|aggregate|consolidate|union)\b",
        r"\b(collect|gather|accumulate|batch)\b",
        r"\b(sync|synchronize|replicate)\b.*\b(across|between|all)\b",
    ],
}

# ── Entity Patterns ─────────────────────────────────────────────────────

ENTITY_PATTERNS = {
    "identifier": r"\b(?:id|ID|#)\s*[:\s]?\s*(\w+(?:\d+))",
    "numeric_id": r"\b(\d{3,})\b",
    "email": r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
    "api_name": r"\b(?:from|via|using|through)\s+(\w+(?:\s+\w+)?)\b",
    "threshold": (
        r"\b(?:greater|less|above|below|more|fewer|over|under)\s+"
        r"(?:than\s+)?(\d+(?:\.\d+)?)\b"
    ),
    "field_name": r"\b(?:field|column|attribute|property)\s+['\"]?(\w+)['\"]?\b",
}


class ParsedIntent:
    """Structured representation of a parsed natural-language intent."""

    def __init__(
        self,
        raw_intent: str = "",
        operations: list[dict[str, Any]] | None = None,
        entities: dict[str, list[str]] | None = None,
        conditions: list[dict[str, Any]] | None = None,
        confidence: float = 0.0,
    ):
        self.raw_intent = raw_intent
        self.operations = operations or []
        self.entities = entities or {}
        self.conditions = conditions or []
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_intent": self.raw_intent,
            "operations": self.operations,
            "entities": self.entities,
            "conditions": self.conditions,
            "confidence": round(self.confidence, 3),
        }


class IntentParser:
    """
    Parses natural-language intents into structured API workflows.

    The parser uses a combination of:
    1. Pattern matching for operation detection
    2. Named entity extraction for parameters
    3. Dependency inference from sentence structure
    4. Condition parsing for conditional workflows

    Usage:
        parser = IntentParser()
        result = parser.parse(
            "Fetch customer 12345 from CRM, enrich with credit score, "
            "and create a loan application if score > 700"
        )
        # result.operations = [
        #     {"type": "api_call", "verb": "fetch", "target": "customer 12345"},
        #     {"type": "transform", "verb": "enrich", "target": "credit score"},
        #     {"type": "condition", "condition": "score > 700",
        #      "then": {"type": "api_call", "verb": "create", "target": "loan application"}}
        # ]
    """

    def __init__(
        self,
        custom_patterns: dict[str, list[str]] | None = None,
        custom_entities: dict[str, str] | None = None,
    ):
        self.operation_patterns = {**OPERATION_PATTERNS}
        if custom_patterns:
            for key, patterns in custom_patterns.items():
                if key in self.operation_patterns:
                    self.operation_patterns[key].extend(patterns)
                else:
                    self.operation_patterns[key] = patterns

        self.entity_patterns = {**ENTITY_PATTERNS}
        if custom_entities:
            self.entity_patterns.update(custom_entities)

    def parse(self, intent: str) -> dict[str, Any]:
        """
        Parse a natural-language intent into a structured workflow.

        Returns a dictionary with operations, entities, conditions,
        and a confidence score.
        """
        if not intent.strip():
            return ParsedIntent(confidence=0.0).to_dict()

        # Step 1: Split into clauses
        clauses = self._split_clauses(intent)

        # Step 2: Extract operations from each clause
        operations: list[dict[str, Any]] = []
        for i, clause in enumerate(clauses):
            ops = self._extract_operations(clause, index=i)
            operations.extend(ops)

        # Step 3: Extract entities
        entities = self._extract_entities(intent)

        # Step 4: Parse conditions
        conditions = self._extract_conditions(intent)

        # Step 5: Infer dependencies
        operations = self._infer_dependencies(operations)

        # Step 6: Calculate confidence
        confidence = self._calculate_confidence(operations, entities)

        parsed = ParsedIntent(
            raw_intent=intent,
            operations=operations,
            entities=entities,
            conditions=conditions,
            confidence=confidence,
        )

        logger.info(
            "Parsed intent into %d operations (confidence=%.2f): %s",
            len(operations),
            confidence,
            intent[:80],
        )

        return parsed.to_dict()

    def _split_clauses(self, intent: str) -> list[str]:
        """Split intent into logical clauses."""
        # Split on conjunctions and commas
        separators = r",\s*(?:and|then|after that|next|finally|also)\s*|,\s+"
        clauses = re.split(separators, intent, flags=re.IGNORECASE)
        # Also split on standalone conjunctions
        result: list[str] = []
        for clause in clauses:
            sub = re.split(r"\s+(?:and then|then|and)\s+", clause, flags=re.IGNORECASE)
            result.extend(s.strip() for s in sub if s.strip())
        return result

    def _extract_operations(self, clause: str, index: int = 0) -> list[dict[str, Any]]:
        """Extract operations from a single clause."""
        operations: list[dict[str, Any]] = []
        clause_lower = clause.lower()

        for op_type, patterns in self.operation_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, clause_lower)
                if match:
                    verb = match.group(1) if match.lastindex else match.group(0)
                    target = self._extract_target(clause, match.end())
                    operations.append(
                        {
                            "name": f"{verb}_{index}",
                            "type": op_type,
                            "verb": verb.strip(),
                            "target": target,
                            "raw_clause": clause,
                            "parameters": self._extract_inline_params(clause),
                            "inputs_from": [],
                            "required_tags": self._infer_tags(clause),
                        }
                    )
                    break  # One operation per pattern category per clause

        # Fallback: if no patterns matched, create a generic operation
        if not operations:
            operations.append(
                {
                    "name": f"generic_{index}",
                    "type": "api_call",
                    "verb": "execute",
                    "target": clause.strip(),
                    "raw_clause": clause,
                    "parameters": {},
                    "inputs_from": [],
                    "required_tags": self._infer_tags(clause),
                }
            )

        return operations

    def _extract_target(self, clause: str, verb_end: int) -> str:
        """Extract the target/object of an operation verb."""
        remaining = clause[verb_end:].strip()
        # Remove common prepositions
        remaining = re.sub(
            r"^(?:the|a|an|from|to|in|on|at|with|for)\s+",
            "",
            remaining,
            flags=re.IGNORECASE,
        )
        # Take until next separator or end
        match = re.match(r"([^,;]+)", remaining)
        return match.group(1).strip() if match else remaining.strip()

    def _extract_entities(self, intent: str) -> dict[str, list[str]]:
        """Extract named entities from the full intent."""
        entities: dict[str, list[str]] = {}
        for entity_type, pattern in self.entity_patterns.items():
            matches = re.findall(pattern, intent, re.IGNORECASE)
            if matches:
                entities[entity_type] = matches
        return entities

    def _extract_conditions(self, intent: str) -> list[dict[str, Any]]:
        """Extract conditional logic from the intent."""
        conditions: list[dict[str, Any]] = []

        # Pattern: "if X then Y"
        if_then = re.findall(
            r"if\s+(.+?)\s+(?:then\s+)?(?:do\s+)?(.+?)(?:\.|$)",
            intent,
            re.IGNORECASE,
        )
        for condition, action in if_then:
            conditions.append(
                {
                    "type": "if_then",
                    "condition": condition.strip(),
                    "action": action.strip(),
                }
            )

        # Pattern: "X > N"
        comparisons = re.findall(
            r"(\w+)\s*(>|<|>=|<=|==|!=)\s*(\d+(?:\.\d+)?)",
            intent,
        )
        for field, operator, value in comparisons:
            conditions.append(
                {
                    "type": "comparison",
                    "field": field,
                    "operator": operator,
                    "value": float(value),
                }
            )

        return conditions

    def _extract_inline_params(self, clause: str) -> dict[str, Any]:
        """Extract inline parameters from a clause."""
        params: dict[str, Any] = {}

        # Extract numeric IDs
        ids = re.findall(r"\b(\d{3,})\b", clause)
        if ids:
            params["id"] = ids[0]

        # Extract quoted strings
        quoted = re.findall(r'"([^"]+)"', clause)
        if quoted:
            params["value"] = quoted[0]

        return params

    def _infer_tags(self, clause: str) -> list[str]:
        """Infer capability tags from clause content."""
        tags: list[str] = []
        tag_keywords = {
            "customer": ["customer", "crm", "client", "account"],
            "order": ["order", "purchase", "transaction", "cart"],
            "inventory": ["inventory", "stock", "warehouse", "product"],
            "payment": ["payment", "billing", "invoice", "charge"],
            "credit": ["credit", "score", "rating", "risk"],
            "notification": ["notify", "alert", "email", "sms", "message"],
        }

        clause_lower = clause.lower()
        for tag, keywords in tag_keywords.items():
            if any(kw in clause_lower for kw in keywords):
                tags.append(tag)

        return tags

    def _infer_dependencies(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Infer data dependencies between operations.

        Uses output-input analysis: if a later operation's target
        references a concept from an earlier operation's output,
        it depends on that earlier operation.
        """
        for i, op in enumerate(operations):
            if i == 0:
                continue

            # Simple heuristic: sequential operations with related targets
            prev_op = operations[i - 1]
            prev_target_words = set(prev_op.get("target", "").lower().split())
            curr_clause_words = set(op.get("raw_clause", "").lower().split())

            # If current clause references previous target, add dependency
            if prev_target_words & curr_clause_words:
                op["inputs_from"].append(prev_op["name"])

        return operations

    def _calculate_confidence(
        self,
        operations: list[dict[str, Any]],
        entities: dict[str, list[str]],
    ) -> float:
        """
        Calculate parsing confidence score (0.0 to 1.0).

        Factors:
        - Number of detected operations (more = higher confidence)
        - Entity extraction success
        - Pattern match specificity
        """
        if not operations:
            return 0.0

        op_score = min(len(operations) / 3.0, 1.0) * 0.5
        entity_score = min(len(entities) / 2.0, 1.0) * 0.3
        specificity = (
            sum(1 for op in operations if op["type"] != "api_call") / max(len(operations), 1) * 0.2
        )

        return min(op_score + entity_score + specificity, 1.0)
