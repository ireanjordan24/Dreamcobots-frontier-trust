#!/usr/bin/env python3
"""Deterministically verify task outcomes from hashed local evidence artifacts."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "dreamco.task_outcome_evidence.v1"
ASSESSMENT_SCHEMA = "dreamco.task_outcome_assessment.v1"
VALID_RESULTS = {"pass", "fail", "unknown"}

def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

def _aware_timestamp(value: Any) -> bool:
    if not _nonempty(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None

def _artifact(root: Path, relative_path: str) -> Path | None:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None

def assess(bundle: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(bundle, dict) or bundle.get("schema") != SCHEMA:
        return {
            "schema": ASSESSMENT_SCHEMA, "status": "inconclusive",
            "verified_success": False,
            "errors": ["invalid or missing evidence bundle schema"],
            "verified_artifact_count": 0,
        }

    task = bundle.get("task")
    if not isinstance(task, dict) or not _nonempty(task.get("id")):
        errors.append("task.id must be a non-empty string")
        task = {}
    criteria = task.get("success_criteria", [])
    if not isinstance(criteria, list) or not criteria:
        errors.append("task.success_criteria must be a non-empty list")
        criteria = []
    criterion_ids = []
    for index, criterion in enumerate(criteria):
        if (not isinstance(criterion, dict)
                or not _nonempty(criterion.get("id"))
                or not _nonempty(criterion.get("description"))):
            errors.append(f"success criterion {index} needs non-empty id and description")
        else:
            criterion_ids.append(criterion["id"])
    if len(criterion_ids) != len(set(criterion_ids)):
        errors.append("success criterion IDs must be unique")

    evidence = bundle.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append("evidence must be a list")
        evidence = []
    valid_ids, seen_ids = set(), set()
    verified_count = 0
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence item {index} must be an object")
            continue
        evidence_id = item.get("id")
        if not _nonempty(evidence_id):
            errors.append(f"evidence item {index} has no valid id")
            continue
        if evidence_id in seen_ids:
            errors.append(f"duplicate evidence id: {evidence_id}")
            continue
        seen_ids.add(evidence_id)
        relative_path, expected_hash = item.get("path"), item.get("sha256")
        if not _nonempty(relative_path) or not _nonempty(expected_hash):
            errors.append(f"evidence {evidence_id} requires path and sha256")
            continue
        if (len(expected_hash) != 64
                or any(char not in "0123456789abcdef" for char in expected_hash.lower())):
            errors.append(f"evidence {evidence_id} has invalid SHA-256 format")
            continue
        if not _nonempty(item.get("source")):
            errors.append(f"evidence {evidence_id} requires source")
            continue
        if not _aware_timestamp(item.get("observed_at")):
            errors.append(f"evidence {evidence_id} requires timezone-aware observed_at")
            continue
        artifact_path = _artifact(evidence_root, relative_path)
        if artifact_path is None:
            errors.append(f"evidence {evidence_id} artifact is missing or outside evidence root")
            continue
        try:
            actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"evidence {evidence_id} artifact cannot be read: {exc}")
            continue
        if actual_hash != expected_hash.lower():
            errors.append(f"evidence {evidence_id} SHA-256 mismatch")
            continue
        valid_ids.add(evidence_id)
        verified_count += 1

    results = bundle.get("criterion_results", [])
    if not isinstance(results, list):
        errors.append("criterion_results must be a list")
        results = []
    by_id = {}
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            errors.append(f"criterion result {index} must be an object")
            continue
        criterion_id = result.get("criterion_id")
        if not _nonempty(criterion_id):
            errors.append(f"criterion result {index} has no criterion_id")
            continue
        if criterion_id in by_id:
            errors.append(f"duplicate result for criterion: {criterion_id}")
            continue
        by_id[criterion_id] = result
        status, refs = result.get("status"), result.get("evidence_ids", [])
        if not isinstance(status, str) or status not in VALID_RESULTS:
            errors.append(f"criterion {criterion_id} has invalid status")
            continue
        if (not isinstance(refs, list) or not refs
                or any(not _nonempty(ref) for ref in refs)):
            errors.append(f"criterion {criterion_id} requires non-empty string evidence_ids")
            continue
        missing_refs = [ref for ref in refs if ref not in valid_ids]
        if missing_refs:
            errors.append(f"criterion {criterion_id} references unverified evidence: {missing_refs}")

    expected_ids, actual_ids = set(criterion_ids), set(by_id)
    for missing in sorted(expected_ids - actual_ids):
        errors.append(f"missing result for criterion: {missing}")
    for extra in sorted(actual_ids - expected_ids):
        errors.append(f"result references unknown criterion: {extra}")
    statuses = [by_id[cid].get("status") for cid in criterion_ids if cid in by_id]
    if errors:
        status = "inconclusive"
    elif "fail" in statuses:
        status = "failed"
    elif statuses and all(value == "pass" for value in statuses):
        status = "verified_success"
    else:
        status = "inconclusive"
    return {
        "schema": ASSESSMENT_SCHEMA, "task_id": task.get("id"),
        "status": status, "verified_success": status == "verified_success",
        "criterion_count": len(criterion_ids),
        "passed_criteria": sum(value == "pass" for value in statuses),
        "failed_criteria": sum(value == "fail" for value in statuses),
        "unknown_criteria": sum(value == "unknown" for value in statuses),
        "verified_artifact_count": verified_count, "errors": errors,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="JSON evidence bundle")
    parser.add_argument("--evidence-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "status": "inconclusive", "verified_success": False,
            "errors": [f"cannot read evidence bundle: {exc}"],
        }, indent=2))
        return 2
    assessment = assess(bundle, args.evidence_root)
    rendered = json.dumps(assessment, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return {"verified_success": 0, "failed": 1, "inconclusive": 2}[assessment["status"]]

if __name__ == "__main__":
    raise SystemExit(main())
