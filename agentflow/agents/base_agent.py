"""
Base Agent — abstract foundation for all orchestration agents.

Agents are autonomous units that collaborate through the shared
OrchestrationContext. Each agent has a specific role in the
orchestration lifecycle and can communicate with other agents
via context events.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from agentflow.core.context import EventType, OrchestrationContext

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for orchestration agents.

    Each agent has:
    - A unique identity for audit tracking
    - Access to the shared OrchestrationContext
    - Ability to emit events to the journal
    - A defined role in the orchestration pipeline
    """

    def __init__(
        self,
        agent_id: str | None = None,
        name: str = "BaseAgent",
        config: dict[str, Any] | None = None,
    ):
        self.agent_id = agent_id or f"{name.lower()}-{uuid.uuid4().hex[:6]}"
        self.name = name
        self.config = config or {}
        self._logger = logging.getLogger(f"agentflow.agents.{name}")

    def emit_event(
        self,
        context: OrchestrationContext,
        event_type: EventType,
        message: str = "",
        step_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Record an event in the orchestration journal."""
        context.record_event(
            event_type=event_type,
            agent_id=self.agent_id,
            step_id=step_id,
            payload=payload or {},
            message=message,
        )
        self._logger.debug("[%s] %s: %s", self.agent_id, event_type.value, message)

    @abstractmethod
    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> Any:
        """Execute the agent's primary function."""
        ...
