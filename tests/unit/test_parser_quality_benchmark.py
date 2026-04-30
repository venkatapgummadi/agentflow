"""
Smoke tests for the parser-quality benchmark + intent corpus.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import pytest

from agentflow.nlp.intent_parser import IntentParser
from experiments.intent_corpus import CORPUS, by_domain
from experiments.parser_quality_benchmark import (
    Score,
    aggregate,
    evaluate_parser,
)


def test_corpus_size_and_balance():
    assert len(CORPUS) == 40
    counts = {k: len(v) for k, v in by_domain().items()}
    assert counts == {"fintech": 10, "healthtech": 10, "ecommerce": 10, "insurance": 10}


def test_corpus_has_no_empty_intents():
    for item in CORPUS:
        assert item.intent.strip()
        assert item.ops, f"intent without expected ops: {item.intent}"


@pytest.mark.asyncio
async def test_evaluate_rule_parser_returns_scores_in_range():
    overall, per_dom = await evaluate_parser(IntentParser())
    for s in [overall, *per_dom.values()]:
        for v in (s.op_recall, s.op_overgeneration, s.entity_f1, s.condition_recall):
            assert 0.0 <= v <= 1.0


def test_aggregate_handles_empty_list():
    s = aggregate([])
    assert s == Score(0.0, 0.0, 0.0, 0.0)


def test_aggregate_averages_correctly():
    s = aggregate([Score(1.0, 0.0, 1.0, 1.0), Score(0.0, 1.0, 0.0, 0.0)])
    assert s.op_recall == 0.5
    assert s.op_overgeneration == 0.5
    assert s.entity_f1 == 0.5
    assert s.condition_recall == 0.5


@pytest.mark.asyncio
async def test_rule_parser_beats_floor():
    """Sanity: the rule parser should at least extract numeric entities competently."""
    overall, _ = await evaluate_parser(IntentParser())
    assert overall.entity_f1 >= 0.5
