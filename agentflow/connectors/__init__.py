"""API platform connectors (MuleSoft, AWS API Gateway, Azure APIM, REST, GraphQL)."""

from agentflow.connectors.aws.client import AWSAPIGatewayConfig, AWSAPIGatewayConnector
from agentflow.connectors.azure.client import AzureAPIMConfig, AzureAPIMConnector
from agentflow.connectors.base import APIEndpoint, APIResponse, BaseConnector
from agentflow.connectors.graphql.client import GraphQLConnector
from agentflow.connectors.mulesoft.client import MuleSoftConnector
from agentflow.connectors.rest.client import RESTConnector

__all__ = [
    "APIEndpoint",
    "APIResponse",
    "BaseConnector",
    "MuleSoftConnector",
    "AWSAPIGatewayConnector",
    "AWSAPIGatewayConfig",
    "AzureAPIMConnector",
    "AzureAPIMConfig",
    "RESTConnector",
    "GraphQLConnector",
]
