"""
Head-to-head quality benchmark: rule-based vs LLM-backed intent parser.

Reviewers 2, 3 and 4 asked for evidence the LLM-backed parser actually
parses better than the rule parser, especially on domain-specific
language. This script scores both parsers against the hand-labelled
corpus in ``experiments.intent_corpus`` on four metrics:

* **op_recall** -- fraction of expected verbs the parser produced.
* **op_overgeneration** -- fraction of produced verbs not in gold.
* **entity_f1** -- F1 over expected numeric entities.
* **condition_recall** -- fraction of expected conditional clauses.

Usage::

    python -m experiments.parser_quality_benchmark
    python -m experiments.parser_quality_benchmark --json
    python -m experiments.parser_quality_benchmark --by-domain

The default LLM provider is the bundled ``DeterministicMockProvider``
so the script is hermetic. Plug in a real provider via
``CallableLLMProvider`` to evaluate a real model -- the script will
report identically structured numbers either way.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from dataclasses import dataclass
from typing import Any

from agentflow.nlp.hybrid_intent_parser import HybridIntentParser
from agentflow.nlp.intent_parser import IntentParser
from agentflow.nlp.llm_intent_parser import LLMIntentParser
from agentflow.nlp.llm_provider import DeterministicMockProvider
from experiments.intent_corpus import CORPUS, LabelledIntent, by_domain


@dataclass
class Score:
    op_recall: float
    op_overgeneration: float
    entity_f1: float
    condition_recall: float

    def as_row(self) -> dict[str, Any]:
        return {
            "op_recall": round(self.op_recall, 3),
            "op_overgeneration": round(self.op_overgeneration, 3),
            "entity_f1": round(self.entity_f1, 3),
            "condition_recall": round(self.condition_recall, 3),
        }


def _normalize_verb(v: str) -> str:
    """
    Map surface verbs to the canonical set used in the gold labels.

    The rule parser produces surface forms ('get', 'fetch'); the gold
    labels use the same surface form, so the normaliser only collapses
    obvious synonyms.
    """
    v = v.lower().strip()
    syn = {
        "retrieve": "retrieve", "lookup": "lookup", "fetch": "fetch", "get": "get",
        "create": "create", "open": "open", "submit": "submit", "post": "post",
        "register": "register", "update": "update", "patch": "update",
        "modify": "update", "set": "update",
        "delete": "cancel", "remove": "cancel", "cancel": "cancel",
        "notify": "notify", "alert": "notify", "email": "email",
        "page": "notify", "sms": "notify",
        "validate": "validate", "verify": "verify", "check": "verify",
        "transfer": "transfer", "refund": "refund", "approve": "approve",
        "trigger": "trigger", "apply": "apply", "adjust": "adjust",
        "reconcile": "reconcile", "forward": "forward", "order": "order",
    }
    return syn.get(v, v)


async def _parse_with(parser: Any, intent: str) -> dict[str, Any]:
    if hasattr(parser, "parse_async"):
        return await parser.parse_async(intent)
    return parser.parse(intent)


def _score(parsed: dict[str, Any], gold: LabelledIntent) -> Score:
    pred_verbs = [_normalize_verb(op.get("verb", "")) for op in parsed.get("operations", [])]
    gold_verbs = [_normalize_verb(v) for v in gold.ops]
    matched = 0
    pred_pool = list(pred_verbs)
    for v in gold_verbs:
        if v in pred_pool:
            pred_pool.remove(v)
            matched += 1
    op_recall = matched / max(len(gold_verbs), 1)
    op_over = len(pred_pool) / max(len(pred_verbs), 1) if pred_verbs else 0.0

    # entity F1 over numeric ids (the gold corpus only labels these for now)
    pred_entities = set(parsed.get("entities", {}).get("numeric_id", []) or [])
    gold_entities = set(gold.entities.get("numeric_id", []) or [])
    if not gold_entities and not pred_entities:
        entity_f1 = 1.0
    elif not gold_entities or not pred_entities:
        entity_f1 = 0.0
    else:
        tp = len(pred_entities & gold_entities)
        precision = tp / len(pred_entities) if pred_entities else 0
        recall = tp / len(gold_entities) if gold_entities else 0
        entity_f1 = (
            2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        )

    # condition recall: did the parser produce at least the expected number of conditions?
    pred_n = len(parsed.get("conditions", []) or [])
    gold_n = gold.conditions
    condition_recall = (
        1.0 if gold_n == 0 else min(pred_n / gold_n, 1.0)
    )

    return Score(
        op_recall=op_recall,
        op_overgeneration=op_over,
        entity_f1=entity_f1,
        condition_recall=condition_recall,
    )


def aggregate(scores: list[Score]) -> Score:
    if not scores:
        return Score(0.0, 0.0, 0.0, 0.0)
    return Score(
        op_recall=statistics.fmean(s.op_recall for s in scores),
        op_overgeneration=statistics.fmean(s.op_overgeneration for s in scores),
        entity_f1=statistics.fmean(s.entity_f1 for s in scores),
        condition_recall=statistics.fmean(s.condition_recall for s in scores),
    )


async def evaluate_parser(parser: Any) -> tuple[Score, dict[str, Score]]:
    by_dom = by_domain()
    overall: list[Score] = []
    per_dom: dict[str, list[Score]] = {d: [] for d in by_dom}
    for item in CORPUS:
        parsed = await _parse_with(parser, item.intent)
        s = _score(parsed, item)
        overall.append(s)
        per_dom[item.domain].append(s)
    return aggregate(overall), {d: aggregate(v) for d, v in per_dom.items()}


def _make_default_llm_parser() -> LLMIntentParser:
    return LLMIntentParser(provider=DeterministicMockProvider())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--by-domain", action="store_true")
    args = parser.parse_args()

    parsers = {
        "rule": IntentParser(),
        "llm-mock": _make_default_llm_parser(),
        "hybrid": HybridIntentParser(),
    }
    out: dict[str, Any] = {"corpus_size": len(CORPUS), "overall": {}, "by_domain": {}}
    for name, p in parsers.items():
        overall, per_dom = asyncio.run(evaluate_parser(p))
        out["overall"][name] = overall.as_row()
        out["by_domain"][name] = {d: s.as_row() for d, s in per_dom.items()}

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Parser quality on {out['corpus_size']} hand-labelled intents")
        print()
        print(f"  {'parser':<10}  op_recall  overgen  entity_F1  cond_recall")
        for name, row in out["overall"].items():
            print(
                f"  {name:<10}  {row['op_recall']:<9}  {row['op_overgeneration']:<7}  "
                f"{row['entity_f1']:<9}  {row['condition_recall']}"
            )
        if args.by_domain:
            print()
            for name in parsers:
                print(f"\n  per-domain ({name}):")
                for d, row in out["by_domain"][name].items():
                    print(
                        f"    {d:<11} op_recall={row['op_recall']:<5} "
                        f"entity_F1={row['entity_f1']:<5} cond={row['condition_recall']}"
                    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
