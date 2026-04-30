# Parser-quality benchmark: rule vs. LLM-backed

> **Why this document exists.** Reviewers 2, 3 and 4 asked for
> evidence the LLM-backed parser actually parses better than the
> rule parser, especially on domain-specific language. This
> document reports **measured** results from the script in
> `experiments/parser_quality_benchmark.py` against the
> hand-labelled corpus in `experiments/intent_corpus.py`.

## Reproduce

```bash
python -m experiments.parser_quality_benchmark --by-domain
```

## Corpus

40 hand-written enterprise intents (fintech: 10, healthtech: 10, ecommerce: 10, insurance: 10). See `experiments/intent_corpus.py` for the full text and gold labels.

## Overall results

| parser    | op_recall | overgeneration | entity F1 | condition_recall |
| --- | --- | --- | --- | --- |
| rule      | 0.55      | 0.45           | 0.936     | 0.95              |
| llm-mock  | 0.487     | 0.312          | 0.0       | 0.775              |
| hybrid    | 0.512     | 0.412          | 0.095     | 0.85              |

## Per-domain breakdown

### rule

| domain     | op_recall | entity F1 | cond_recall |
| --- | --- | --- | --- |
| fintech    | 0.55      | 0.913     | 0.95 |
| healthtech | 0.55      | 0.933     | 1.0 |
| ecommerce  | 0.6       | 0.897     | 0.85 |
| insurance  | 0.5       | 1.0       | 1.0 |

### llm-mock

| domain     | op_recall | entity F1 | cond_recall |
| --- | --- | --- | --- |
| fintech    | 0.45      | 0.0       | 0.7 |
| healthtech | 0.5       | 0.0       | 0.8 |
| ecommerce  | 0.5       | 0.0       | 0.7 |
| insurance  | 0.5       | 0.0       | 0.9 |

### hybrid

| domain     | op_recall | entity F1 | cond_recall |
| --- | --- | --- | --- |
| fintech    | 0.45      | 0.08      | 0.8 |
| healthtech | 0.5       | 0.133     | 1.0 |
| ecommerce  | 0.55      | 0.067     | 0.7 |
| insurance  | 0.55      | 0.1       | 0.9 |

## Honest interpretation

* The **rule parser is competitive** on this corpus; it has the best entity F1 (because numeric IDs are surface-pattern friendly) and the best condition recall.
* The **mock LLM provider** scores poorly on entity F1 because the bundled `DeterministicMockProvider` is intentionally minimal -- it exists for hermetic tests, not as a substitute for a real LLM.
* To see what a real LLM does on this corpus, plug in a real provider via `CallableLLMProvider` and rerun:

```python
from agentflow.nlp import CallableLLMProvider, LLMIntentParser
provider = CallableLLMProvider(my_async_openai_call, name='openai')
parser = LLMIntentParser(provider=provider)
# then re-run experiments/parser_quality_benchmark.py with `parser` patched in
```

## What this changes

* The hybrid parser still wins for **flexibility** (it can fall back to the rule path under `deterministic=True`).
* Real measurements should replace the mock numbers above before the camera-ready submission. The corpus and the scoring code are now in place; only the provider needs to be swapped.
