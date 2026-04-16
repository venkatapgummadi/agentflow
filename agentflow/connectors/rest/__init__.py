"""Generic REST/HTTP connector with OpenAPI-driven discovery."""

from agentflow.connectors.rest.auth import (
    ApiKeyAuth,
    AuthStrategy,
    BasicAuth,
    BearerTokenAuth,
    NoAuth,
)
from agentflow.connectors.rest.client import RESTConnector

__all__ = [
    "RESTConnector",
    "AuthStrategy",
    "NoAuth",
    "ApiKeyAuth",
    "BearerTokenAuth",
    "BasicAuth",
]
