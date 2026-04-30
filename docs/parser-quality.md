# Parser-quality benchmark: rule vs. LLM-backed

> **Why this document exists.** Reviewers 2, 3 and 4 asked for
> evidence the LLM-backed parser actually parses better than the
> rule parser, especially on domain-specific language. This
> document reports **measured** results from the script in
> `experiments/parser_quality_benchmark.py` against the
> hand-labelled corpus in `experiments/intent_corpus.py`.

> :warning: **Important caveat.** The `llm-mock` and `hybrid` rows below
> use `DeterministicMockProvider`, which is intentionally minimal
> (it exists for hermetic tests, not production parsing). To get
> real LLM numbers, plug in a real provider via
> `CallableLLMProvider` and rerun -- see the snippet at the bottom
> of this document.

## Reproduce

```bash
python -m experiments.parser_quality_benchmark --by-domain
```

## Corpus

40 hand-written enterprise intents (fintech: 10, healthtech: 10, ecommerce: 10, insurance: 10). See `experiments/intent_corpus.py` for the full text and gold labels.

**Limits to keep in mind.** 40 intents is a sanity baseline, not an empirical study.
There is no inter-annotator agreement, no stratified sampling, and gold
entity labels currently cover numeric IDs only (other entity types are
on the roadmap). Treat the numbers below as a regression detector for
AgentFlow contributors, not as the final word on parser quality.

## Overall results

| parser    | op_recall | overgeneration | entity F1 | condition_recall |
| --- | --- | --- | --- | --- |
| rule      | 0.988     | 0.037          | 0.936     | 0.95              |
| llm-mock  | 0.487     | 0.312          | 0.0       | 0.775              |
| hybrid    | 0.613     | 0.325          | 0.095     | 0.85              |

## Per-domain breakdown

### rule

| domain     | op_recall | entity F1 | cond_recall |
| --- | --- | --- | --- |
| fintech    | 1.0       | 0.913     | 0.95 |
| healthtech | 1.0       | 0.933     | 1.0 |
| ecommerce  | 0.95      | 0.897     | 0.85 |
| insurance  | 1.0       | 1.0       | 1.0 |

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
| fintech    | 0.55      | 0.08      | 0.8 |
| healthtech | 0.7       | 0.133     | 1.0 |
| ecommerce  | 0.6       | 0.067     | 0.7 |
| insurance  | 0.6       | 0.1       | 0.9 |

## Honest interpretation

* The **rule parser is now strong** on this corpus (op_recall close to 1.0) after the v1.1.2 verb-pattern expansion. It also retains the highest entity F1 because numeric IDs are surface-pattern friendly.
* The **mock LLM provider** scores poorly on entity F1 because the bundled `DeterministicMockProvider` extracts no entities. This is by design -- the provider is a deterministic test harness, not a real model.
* The **hybrid parser** sits in the middle: it inherits the LLM mock's verb canonicalisation but falls back to the rule parser when the LLM is empty. With a real LLM provider plugged in, the hybrid is the recommended production path.

## Plug in a real LLM and rerun

```python
from agentflow.nlp import CallableLLMProvider, LLMIntentParser
from experiments.parser_quality_benchmark import evaluate_parser
import asyncio

async def call_openai(req):
    # ... your async OpenAI call returning a JSON string ...
    return json_string

provider = CallableLLMProvider(call_openai, name='openai', model='gpt-4o-mini')
parser = LLMIntentParser(provider=provider)
overall, per_dom = asyncio.run(evaluate_parser(parser))
print(overall.as_row())
```
