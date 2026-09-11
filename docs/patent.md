# Patent

The integration-workflow architecture implemented in AgentFlow is the
subject of Indian Patent Application No. **202641090631**.

| Field | Record |
|---|---|
| Title | A Computer Implemented Provenance Aware Integration Workflow Management System |
| Application number | 202641090631 |
| Applicant / inventor | Venkata Pavan Kumar Gummadi |
| Filing date | 24 July 2026 |
| Publication | 31 July 2026 (Patents Act, 1970, Section 11A) |
| Office | Indian Patent Office |
| Public search | [IP India Public Search](https://iprsearch.ipindia.gov.in/PublicSearch/) — query `202641090631` |

The published specification describes a provenance-aware integration-workflow
system that keeps a canonical workflow representation consistent through
authoring, shared semantic validation, artifact generation, deployment
verification, and runtime execution.

In this repository those ideas appear as:

- DAG execution plans as the canonical workflow representation
  ([Architecture](architecture.md#dag-based-execution-model))
- Planner / Executor / Validator agents applying shared validation before
  execution ([Architecture](architecture.md#multi-agent-system))
- An append-only event journal that records orchestration provenance
  ([Architecture](architecture.md#event-journal-and-audit-trail))

Use of this software is licensed under [Apache License 2.0](../LICENSE).
That license includes an express patent grant from contributors.

Cite the application as:

```
Gummadi, V. P. K. (2026). A Computer Implemented Provenance Aware
Integration Workflow Management System. Indian Patent Application
No. 202641090631. Indian Patent Office.
```

See [`CITATION.cff`](../CITATION.cff) for machine-readable citation metadata.
