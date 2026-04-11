"""
Base Connector — abstract interface for all API platform connectors.

Every connector (MuleSoft, REST, GraphQL, gRPC) implements this interface
so the orchestrator can interact with any platform uniformly.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class APIEndpoint:
    """Metadata for a discovered API endpoint."""

    endpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    method: str = "GET"
    path: str = ""
    description: str = ""
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    response_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)
    latency_p95_ms: float = 0.0
    cost_per_call: float = 0.0
    rate_limit_rpm: int = 0
    connector_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "description": self.description,
            "tags": self.tags,
            "latency_p95_ms": self.latency_p95_ms,
            "cost_per_call": self.cost_per_call,
            "rate_limit_rpm": self.rate_limit_rpm,
            "connector_id": self.connector_id,
        }


@dataclass
class APIResponse:
    """Standardized response from any connector."""

    status_code: int = 200
    body: Any = None
    headers: Dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0
    connector_id: str = ""
    endpoint_id: str = ""
    is_error: bool = False
    error_message: str = ""
    retryable: bool = False

    @property
    def success(self) -> bool:
        return not self.is_error and 200 <= self.status_code < 300


class BaseConnector(ABC):
    """
    Abstract base for all API platform connectors.

    Subclasses must implement:
    - discover(): Find available APIs on the platform
    - invoke(): Execute a specific API call
    - health_check(): Verify connectivity
    """

    def __init__(
        self,
        connector_id: Optional[str] = None,
        name: str = "",
        config: Optional[Dict[str, Any]] = None,
    ):
        self.connector_id = connector_id or str(uuid.uuid4())[:8]
        self.name = name
        self.config = config or {}
        self._endpoints: Dict[str, APIEndpoint] = {}

    @abstractmethod
    def discover(self) -> List[Dict[str, Any]]:
        """
        Discover available APIs on this platform.

        Returns a list of API endpoint metadata dictionaries
        that the PlannerAgent uses for capability matching.
        """
        ...

    @abstractmethod
    async def invoke(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        """
        Execute an API operation.

        Args:
            operation: Operation identifier (e.g., "GET /customers/{id}").
            parameters: Request parameters (path, query, body).
            headers: Additional HTTP headers.
            timeout_ms: Request timeout.

        Returns:
            Standardized APIResponse.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify connectivity to the platform."""
        ...

    def register_endpoint(self, endpoint: APIEndpoint) -> None:
        """Register a discovered endpoint."""
        endpoint.connector_id = self.connector_id
        self._endpoints[endpoint.endpoint_id] = endpoint

    def get_endpoint(self, endpoint_id: str) -> Optional[APIEndpoint]:
        """Retrieve endpoint metadata."""
        return self._endpoints.get(endpoint_id)

    @property
    def endpoints(self) -> List[APIEndpoint]:
        return list(self._endpoints.values())
