# Buddy Task Outcome Evidence Verifier

## Purpose

Prevent Buddy and its specialist bots from reporting a task as complete merely because a model or tool says it succeeded. The verifier checks explicit success criteria against local evidence artifacts whose SHA-256 digests, provenance labels, and timezone-aware observation timestamps are recorded in a JSON bundle.

This is a deterministic evidence-integrity check, not a semantic judge. A human or trusted task-specific grader must still decide whether an artifact satisfies a criterion. The verifier does not execute tools, call models, access networks, or authorize side effects.

## Status semantics

- `verified_success`: every declared criterion has a `pass` result backed by at least one verified artifact.
- `failed`: at least one criterion is explicitly `fail`, and the bundle has no structural or evidence-integrity errors.
- `inconclusive`: missing/unknown results, malformed data, missing artifacts, invalid timestamps, unsafe paths, or hash mismatches.

Exit codes: 0 = verified_success; 1 = failed; 2 = inconclusive or unreadable input. Only exit code 0 means the evidence bundle passed this validator.

## Bundle format

```json
{
  "schema": "dreamco.task_outcome_evidence.v1",
  "task": {
    "id": "task-001",
    "success_criteria": [
      {"id": "artifact-created", "description": "Expected output file exists"}
    ]
  },
  "evidence": [
    {
      "id": "proof-1",
      "path": "artifacts/output.txt",
      "sha256": "<64-character SHA-256 hex digest>",
      "source": "local-test-run",
      "observed_at": "2026-11-08T18:00:00-06:00"
    }
  ],
  "criterion_results": [
    {
      "criterion_id": "artifact-created",
      "status": "pass",
      "evidence_ids": ["proof-1"]
    }
  ]
}
```

Artifact paths are resolved under the supplied evidence root; path traversal and symlink escapes are rejected. Every referenced evidence item must exist, be readable, have a matching SHA-256 digest, a source label, and a timezone-aware timestamp.

## Run locally

```bash
python3 -m unittest tests.test_verify_task_outcome -v
python3 tools/verify_task_outcome.py path/to/bundle.json \
  --evidence-root path/to/evidence-root \
  --output path/to/assessment.json
```

## Integration rules

1. Keep task success criteria separate from model-generated narratives.
2. Record artifacts before asking any model to summarize the run.
3. Use a deterministic grader or human review to populate criterion results.
4. Treat `inconclusive` as not complete; request more evidence rather than guessing.
5. Keep approval and permission checks outside this verifier. Passing it never authorizes publishing, spending, account changes, or physical actuation.
6. Do not store secrets, personal video, hidden benchmark answers, or restricted training data in evidence artifacts.
7. This verifier hashes local files only. Remote URLs, screenshots, model claims, and connector acknowledgements require a separate trusted capture adapter and must not be represented as locally verified artifacts.

## Known limitations

A valid hash proves that the bytes match the recorded digest, not that the artifact is truthful, complete, or semantically sufficient. The provenance source label is descriptive and is not cryptographically authenticated. Production use should add signed capture receipts, trusted timestamps, task-specific graders, retention controls, and an independent review policy.
