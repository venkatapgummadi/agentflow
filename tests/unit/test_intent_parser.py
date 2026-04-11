"""
Tests for the IntentParser NLP module.

Verifies intent decomposition, entity extraction, and condition parsing.

Author: Venkata Pavan Kumar Gummadi
"""

from agentflow.nlp.intent_parser import IntentParser


class TestIntentParser:
    """Test natural language intent parsing."""

    def setup_method(self):
        self.parser = IntentParser()

    def test_simple_fetch_intent(self):
        result = self.parser.parse("Fetch customer 12345")
        assert len(result["operations"]) >= 1
        assert result["operations"][0]["verb"] == "fetch"

    def test_multi_operation_intent(self):
        result = self.parser.parse(
            "Fetch customer from CRM, enrich with credit score, and create loan"
        )
        assert len(result["operations"]) >= 2

    def test_entity_extraction_numeric_id(self):
        result = self.parser.parse("Get customer 12345 from database")
        entities = result["entities"]
        assert "numeric_id" in entities
        assert "12345" in entities["numeric_id"]

    def test_condition_extraction(self):
        result = self.parser.parse(
            "If score > 700 then create application"
        )
        assert len(result["conditions"]) >= 1

    def test_empty_intent(self):
        result = self.parser.parse("")
        assert result["confidence"] == 0.0

    def test_confidence_increases_with_detail(self):
        simple = self.parser.parse("Get data")
        detailed = self.parser.parse(
            "Fetch customer 12345 from CRM, enrich with credit score 700"
        )
        assert detailed["confidence"] >= simple["confidence"]

    def test_transform_operation_detected(self):
        result = self.parser.parse("Enrich the customer record with address data")
        ops = result["operations"]
        transform_ops = [op for op in ops if op["type"] == "transform"]
        assert len(transform_ops) >= 1

    def test_aggregate_operation_detected(self):
        result = self.parser.parse(
            "Combine inventory data across all warehouses"
        )
        ops = result["operations"]
        agg_ops = [op for op in ops if op["type"] == "aggregate"]
        assert len(agg_ops) >= 1

    def test_tag_inference_customer(self):
        result = self.parser.parse("Fetch customer profile from CRM")
        ops = result["operations"]
        assert any("customer" in op.get("required_tags", []) for op in ops)

    def test_tag_inference_payment(self):
        result = self.parser.parse("Process payment for invoice 9876")
        ops = result["operations"]
        tags = []
        for op in ops:
            tags.extend(op.get("required_tags", []))
        assert "payment" in tags
