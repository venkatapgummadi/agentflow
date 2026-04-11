"""
Orchestration Context — shared state for multi-agent collaboration.

The OrchestrationContext acts as a blackboard architecture where agents
read and write shared state during orchestration. It provides:
- Thread-safe access to execution state
- Event journaling for full auditability
- Scoped variable namespaces per agent
- Dependency tracking between plan steps

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(Enum):
    """Categories of orchestration events for the audit journal."""

    PLAN_CREATED = "plan_created"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_RETRIED = "step_retried"
    AGENT_MESSAGE = "agent_message"
    ROUTE_SELECTED = "route_selected"
    CIRCUIT_OPENED = "circuit_opened"
    CIRCUIT_CLOSED = "circuit_closed"
    FALLBACK_TRIGGERED = "fallback_triggered"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"


@dataclass
class ContextEvent:
    """An immutable record in the orchestration journal."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.AGENT_MESSAGE
    timestamp: float = field(default_factory=time.time)
    agent_id: str = ""
    step_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "step_id": self.step_id,
            "payload": self.payload,
            "message": self.message,
        }


class OrchestrationContext:
    """
    Shared blackboard for multi-agent orchestration.

    Provides thread-safe, namespaced state management with full
    audit journaling. Each agent reads/writes to its own namespace,
    while the orchestrator coordinates cross-agent data flow.

    Usage:
        ctx = OrchestrationContext(intent="Fetch customer and enrich")
        ctx.set("planner", "api_sequence", ["crm.get", "credit.score"])
        sequence = ctx.get("planner", "api_sequence")
    """

    def __init__(
        self,
        intent: str = "",
        orchestration_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.orchestration_id = orchestration_id or str(uuid.uuid4())
        self.intent = intent
        self.metadata = metadata or {}
        self.created_at = time.time()

        # Namespaced agent state
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

        # Immutable event journal
        self._journal: list[ContextEvent] = []

        # Step results indexed by step_id
        self._step_results: dict[str, Any] = {}

        # Dependency graph: step_id -> list of dependent step_ids
        self._dependencies: dict[str, list[str]] = {}

    async def set(self, namespace: str, key: str, value: Any) -> None:
        """Set a value in a namespaced scope (thread-safe)."""
        async with self._lock:
            if namespace not in self._state:
                self._state[namespace] = {}
            self._state[namespace][key] = value

    async def get(
        self, namespace: str, key: str, default: Any = None
    ) -> Any:
        """Get a value from a namespaced scope."""
        async with self._lock:
            return self._state.get(namespace, {}).get(key, default)

    async def get_namespace(self, namespace: str) -> dict[str, Any]:
        """Get the full state for a namespace."""
        async with self._lock:
            return dict(self._state.get(namespace, {}))

    def record_event(
        self,
        event_type: EventType,
        agent_id: str = "",
        step_id: str | None = None,
        payload: dict[str, Any] | None = None,
        message: str = "",
    ) -> ContextEvent:
        """Append an immutable event to the journal."""
        event = ContextEvent(
            event_type=event_type,
            agent_id=agent_id,
            step_id=step_id,
            payload=payload or {},
            message=message,
        )
        self._journal.append(event)
        return event

    def store_step_result(self, step_id: str, result: Any) -> None:
        """Store the result of a completed plan step."""
        self._step_results[step_id] = result

    def get_step_result(self, step_id: str) -> Any:
        """Retrieve a stored step result."""
        return self._step_results.get(step_id)

    def add_dependency(self, step_id: str, depends_on: str) -> None:
        """Register a dependency between steps."""
        if step_id not in self._dependencies:
            self._dependencies[step_id] = []
        self._dependencies[step_id].append(depends_on)

    def get_dependencies(self, step_id: str) -> list[str]:
        """Get all dependencies for a step."""
        return self._dependencies.get(step_id, [])

    def are_dependencies_met(self, step_id: str) -> bool:
        """Check if all dependencies for a step have results."""
        deps = self.get_dependencies(step_id)
        return all(d in self._step_results for d in deps)

    @property
    def journal(self) -> list[ContextEvent]:
        """Read-only access to the event journal."""
        return list(self._journal)

    @property
    def duration(self) -> float:
        """Elapsed time since context creation."""
        return time.time() - self.created_at

    def summary(self) -> dict[str, Any]:
        """Generate an orchestration summary for reporting."""
        event_counts: dict[str, int] = {}
        for event in self._journal:
            key = event.event_type.value
            event_counts[key] = event_counts.get(key, 0) + 1

        return {
            "orchestration_id": self.orchestration_id,
            "intent": self.intent,
            "duration_seconds": round(self.duration, 3),
            "total_events": len(self._journal),
            "event_counts": event_counts,
            "steps_completed": len(self._step_results),
            "namespaces": list(self._state.keys()),
        }
