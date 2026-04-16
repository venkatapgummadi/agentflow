"""
Authentication strategies for the REST connector.

Provides pluggable auth that can be attached to a RESTConnector
without changing the connector logic itself.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod


class AuthStrategy(ABC):
    """Base class for REST authentication strategies."""

    @abstractmethod
    def apply(self, headers: dict[str, str]) -> dict[str, str]:
        """Return a new headers dict with authentication applied."""
        ...


class NoAuth(AuthStrategy):
    """No authentication — used for public endpoints."""

    def apply(self, headers: dict[str, str]) -> dict[str, str]:
        return dict(headers)


class ApiKeyAuth(AuthStrategy):
    """
    API key authentication.

    Adds the key to a configurable header (default: X-API-Key)
    or to a query parameter (handled by the connector).
    """

    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        if not api_key:
            raise ValueError("api_key cannot be empty")
        self.api_key = api_key
        self.header_name = header_name

    def apply(self, headers: dict[str, str]) -> dict[str, str]:
        out = dict(headers)
        out[self.header_name] = self.api_key
        return out


class BearerTokenAuth(AuthStrategy):
    """OAuth2 / JWT bearer token authentication."""

    def __init__(self, token: str):
        if not token:
            raise ValueError("token cannot be empty")
        self.token = token

    def apply(self, headers: dict[str, str]) -> dict[str, str]:
        out = dict(headers)
        out["Authorization"] = f"Bearer {self.token}"
        return out


class BasicAuth(AuthStrategy):
    """HTTP Basic authentication (RFC 7617)."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def apply(self, headers: dict[str, str]) -> dict[str, str]:
        out = dict(headers)
        creds = f"{self.username}:{self.password}".encode()
        encoded = base64.b64encode(creds).decode("ascii")
        out["Authorization"] = f"Basic {encoded}"
        return out
