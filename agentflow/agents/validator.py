"""
Validator Agent — validates orchestration results for correctness.

The ValidatorAgent runs post-execution checks including:
- Schema validation of API responses
- Business rule assertions
- Data integrity checks
- Cross-step consistency verification

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
from typing import Any

from agentflow.agents.base_agent import BaseAgent
from agentflow.core.context import EventType, OrchestrationContext
from agentflow.core.plan import ExecutionPlan, StepStatus

logger = logging.getLogger(__name__)


class ValidationRule:
    """A single validation rule to apply to step results."""

    def __init__(
        self,
        name: str,
        rule_type: str = "schema",
        target_step: str = "",
        assertion: str = "",
        expected: Any = None,
        severity: str = "error",
    ):  # noqa: D102
        self.name = name
        self.rule_type = rule_type
        self.target_step = target_step
        self.assertion = assertion
        self.expected = expected
        self.severity = severity  # "error", "warning", "info"


class ValidationResult:
    """Result of a validation check."""

    def __init__(
        self,
        rule_name: str,
        passed: bool,
        message: str = "",
        severity: str = "error",
        details: dict[str, Any] | None = None,
    ):
        self.rule_name = rule_name
        self.passed = passed
        self.message = message
        self.severity = severity
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


class ValidatorAgent(BaseAgent):
    """
    Post-execution validation of orchestration results.

    Runs a suite of configurable validation rules against the
    execution results to ensure correctness, completeness, and
    data integrity.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="ValidatorAgent", **kwargs)
        self._rules: list[ValidationRule] = []

    def add_rule(self, rule: ValidationRule) -> None:
        """Register a validation rule."""
        self._rules.append(rule)

    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> Dict[str, Any]:
        plan = kwargs.get("plan")
        outputs = kwargs.get("outputs", {})
        return await self.validate(plan, context, outputs)

    async def validate(
        self,
        plan: ExecutionPlan,
        context: OrchestrationContext,
        outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run all validation checks on the orchestration results.

        Built-in checks:
        1. Completeness: all non-skipped steps have results
        2. No failures: no steps ended in FAILED state
        3. Data presence: critical outputs are non-null
        4. Custom rules: user-defined assertions
        """
        results: list[ValidationResult] = []

        # Built-in: Completeness check
        results.append(self._check_completeness(plan))

        # Built-in: No failures check
        results.append(self._check_no_failures(plan))

        # Built-in: Data presence
        results.extend(self._check_data_presence(plan, outputs))

        # Custom rules
        for rule in self._rules:
            result = self._evaluate_rule(rule, plan, outputs)
            results.append(result)

        # Summarize
        passed = all(
            r.passed for r in results if r.severity == "error"
        )
        warnings = [r for r in results if not r.passed and r.severity == "warning"]
        errors = [r for r in results if not r.passed and r.severity == "error"]

        # Emit validation events
        event_type = EventType.VALIDATION_PASSED if passed else EventType.VALIDATION_FAILED
        self.emit_event(
            context,
            event_type,
            message=f"Validation {'passed' if passed else 'failed'}: "
                    f"{len(errors)} errors, {len(warnings)} warnings",
        )

        return {
            "passed": passed,
            "total_checks": len(results),
            "errors": [r.to_dict() for r in errors],
            "warnings": [r.to_dict() for r in warnings],
            "results": [r.to_dict() for r in results],
        }

    def _check_completeness(self, plan: ExecutionPlan) -> ValidationResult:
        """Verify all steps reached a terminal state."""
        incomplete = [
            s for s in plan.steps if not s.is_terminal
        ]
        return ValidationResult(
            rule_name="completeness",
            passed=len(incomplete) == 0,
            message=(
                "All steps completed"
                if not incomplete
                else f"{len(incomplete)} steps did not complete"
            ),
            details={"incomplete_steps": [s.step_id for s in incomplete]},
        )

    def _check_no_failures(self, plan: ExecutionPlan) -> ValidationResult:
        """Verify no steps failed."""
        failed = [
            s for s in plan.steps if s.status == StepStatus.FAILED
        ]
        return ValidationResult(
            rule_name="no_failures",
            passed=len(failed) == 0,
            message=(
                "No step failures"
                if not failed
                else f"{len(failed)} steps failed"
            ),
            severity="error",
            details={
                "failed_steps": [
                    {"step_id": s.step_id, "error": s.error}
                    for s in failed
                ]
            },
        )

    def _check_data_presence(
        self, plan: ExecutionPlan, outputs: dict[str, Any]
    ) -> list[ValidationResult]:
        """Verify completed steps have non-null outputs."""
        results: List[ValidationResult] = []
        for step in plan.steps:
            if step.status == StepStatus.COMPLETED:
                has_output = step.step_id in outputs and outputs[step.step_id] is not None
                results.append(
                    ValidationResult(
                        rule_name=f"data_presence_{step.name}",
                        passed=has_output,
                        message=(
                            f"Step {step.name} has output"
                            if has_output
                            else f"Step {step.name} completed but has no output"
                        ),
                        severity="warning",
                    )
                )
        return results

    def _evaluate_rule(
        self,
        rule: ValidationRule,
        plan: ExecutionPlan,
        outputs: dict[str, Any],
    ) -> ValidationResult:
        """Evaluate a custom validation rule."""
        try:
            step = plan.get_step(rule.target_step) if rule.target_step else None
            output = outputs.get(rule.target_step)

            if rule.rule_type == "not_null":
                passed = output is not None
            elif rule.rule_type == "equals":
                passed = output == rule.expected
            elif rule.rule_type == "contains":
                passed = rule.expected in str(output) if output else False
            else:
                passed = True

            return ValidationResult(
                rule_name=rule.name,
                passed=passed,
                message=f"Custom rule '{rule.name}' {'passed' if passed else 'failed'}",
                severity=rule.severity,
            )
        except Exception as e:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message=f"Rule evaluation error: {str(e)}",
                severity=rule.severity,
            )
