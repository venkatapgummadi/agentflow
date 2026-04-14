"""
Tests for the GraphQLConnector.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio

from agentflow.connectors.graphql import GraphQLConnector


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SIMPLIFIED_SCHEMA = {
    "queries": [
        {
            "name": "getUser",
            "description": "Fetch user by id",
            "tags": ["user", "fetch"],
            "args": [{"name": "id", "type": "ID!"}],
            "latency_p95_ms": 90.0,
            "cost_per_call": 0.0005,
        }
    ],
    "mutations": [
        {
            "name": "createUser",
            "description": "Create a user",
            "tags": ["user", "create"],
            "args": [{"name": "input", "type": "UserInput!"}],
        }
    ],
}


INTROSPECTION_SCHEMA = {
    "__schema": {
        "queryType": {
            "fields": [
                {"name": "ping", "description": "Health probe", "args": []},
            ]
        },
        "mutationType": {
            "fields": [
                {"name": "trigger", "description": "Side effect", "args": []},
            ]
        },
    }
}


class TestGraphQLDiscovery:
    def test_simplified_schema_registers_query_and_mutation(self):
        gql = GraphQLConnector(
            endpoint_url="https://api.example.com/graphql",
            schema=SIMPLIFIED_SCHEMA,
        )
        eps = gql.discover()
        names = {ep["name"] for ep in eps}
        assert "query getUser" in names
        assert "mutation createUser" in names

    def test_introspection_schema_normalized(self):
        gql = GraphQLConnector(
            endpoint_url="https://api.example.com/graphql",
            schema=INTROSPECTION_SCHEMA,
        )
        eps = gql.discover()
        assert {"query ping", "mutation trigger"} == {ep["name"] for ep in eps}

    def test_discover_carries_metadata(self):
        gql = GraphQLConnector(
            endpoint_url="https://api.example.com/graphql",
            schema=SIMPLIFIED_SCHEMA,
        )
        eps = gql.discover()
        get_user = next(ep for ep in eps if ep["name"] == "query getUser")
        assert get_user["latency_p95_ms"] == 90.0
        assert get_user["cost_per_call"] == 0.0005
        assert "query" in get_user["tags"]
        assert "user" in get_user["tags"]


class TestGraphQLInvoke:
    def test_invoke_query_builds_document_with_variables(self):
        gql = GraphQLConnector(
            endpoint_url="https://api.example.com/graphql",
            schema=SIMPLIFIED_SCHEMA,
        )
        resp = _run(gql.invoke("query getUser", {"id": "42"}))
        assert resp.success
        doc = gql.call_log[-1]["document"]
        assert "query getUserOp" in doc
        assert "$id" in doc

    def test_invoke_rejects_unknown_op_type(self):
        gql = GraphQLConnector(endpoint_url="https://api.example.com/graphql")
        resp = _run(gql.invoke("subscription noSuch", {}))
        assert resp.is_error
        assert resp.status_code == 400

    def test_invoke_records_errors_field(self):
        async def upstream(url, doc, vars_, headers, timeout):
            return {
                "status_code": 200,
                "data": None,
                "errors": [{"message": "field not found"}],
            }

        gql = GraphQLConnector(
            endpoint_url="https://api.example.com/graphql",
            gql_call=upstream,
        )
        resp = _run(gql.invoke("query bogus", {}))
        assert resp.is_error
        assert "field not found" in resp.error_message

    def test_invoke_handles_transport_exception(self):
        async def boom(url, doc, vars_, headers, timeout):
            raise TimeoutError("upstream timeout")

        gql = GraphQLConnector(
            endpoint_url="https://api.example.com/graphql",
            gql_call=boom,
        )
        resp = _run(gql.invoke("query getUser", {"id": "1"}))
        assert resp.is_error
        assert resp.retryable is True
