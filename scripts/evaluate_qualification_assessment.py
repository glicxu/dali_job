from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app.config import load_runtime_config  # noqa: E402
from app.modules.matching_v2.prompts import (  # noqa: E402
    QUALIFICATION_SYSTEM_PROMPT,
    build_qualification_user_prompt,
)
from app.modules.matching_v2.qualification import (  # noqa: E402
    OpenAIQualificationMatcher,
    QualificationInput,
    validate_qualification_assessment,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, canonical_json  # noqa: E402
from app.modules.matching_v2.schemas import qualification_response_format  # noqa: E402
from db_common import load_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Stage 3 against frozen candidate/job inputs.")
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument("--job-extraction-report", required=True)
    parser.add_argument("--job-ordinal", type=int, required=True)
    parser.add_argument("--candidate-fixture-id", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_config(args.config)
    runtime = load_runtime_config(args.config)
    job_report = json.loads(Path(args.job_extraction_report).read_text(encoding="utf-8"))
    result = next(
        item for item in job_report["results"]
        if int(item["ordinal"]) == args.job_ordinal and item["status"] == "succeeded"
    )
    fixture_release = json.loads(
        (SERVER / "app" / "modules" / "evaluation" / "candidate_fixtures.v1.json")
        .read_text(encoding="utf-8")
    )
    fixture = next(
        item for item in fixture_release["fixtures"]
        if item["fixture_id"] == args.candidate_fixture_id
    )
    candidate_profile, candidate_evidence = _candidate_input(fixture)
    job_requirements, validation_requirements, group_refs, policies = _job_input(
        result["artifact"]["requirements"]
    )
    career = fixture["coverage"]
    selected_context = {
        "career_profile_id": f"fixture:{fixture['fixture_id']}",
        "role_family": career["role_family"],
        "track": career["track"],
        "level": career["career_stage"],
    }
    allowed_evidence = frozenset(item["span_id"] for item in candidate_evidence)
    qualification_input = QualificationInput(
        candidate_profile=candidate_profile,
        candidate_evidence=tuple(candidate_evidence),
        job_requirements=tuple(job_requirements),
        approved_alternatives=tuple(policies),
        allowed_evidence_refs=allowed_evidence,
        omitted_evidence_refs=(),
        selected_career_context=selected_context,
        allowed_alternative_group_refs=group_refs,
    )
    started = time.monotonic()
    extracted = OpenAIQualificationMatcher(runtime.openai_model).assess(qualification_input)
    validated = validate_qualification_assessment(
        extracted.artifact,
        requirements=validation_requirements,
        allowed_evidence_refs=allowed_evidence,
        allowed_alternative_group_refs=group_refs,
    )
    requirement_ids = [item["requirement_id"] for item in job_requirements]
    user_prompt = build_qualification_user_prompt(
        candidate_profile=candidate_profile,
        candidate_evidence=candidate_evidence,
        job_requirements=job_requirements,
        approved_alternatives=policies,
        career_context=selected_context,
    )
    report = {
        "evaluation_type": "qualification_assessment_only",
        "candidate_fixture_id": fixture["fixture_id"],
        "job_snapshot_id": result["snapshot_id"],
        "job_ordinal": args.job_ordinal,
        "job_title": result["source_title"],
        "model": extracted.model_id,
        "provider_execution_reference": extracted.provider_execution_reference,
        "latency_ms": round((time.monotonic() - started) * 1000, 2),
        "versions": {
            "schema": "qualification-assessment.v2",
            "response_schema": "qualification-assessment-response.v2",
            "prompt": "qualification-match.v2",
            "selection_policy": "career-selection-policy.v2",
            "qualification_policy": "qualification-policy.v2",
            "input_policy": "qualification-input.v2",
            "semantic_validator": "matching-semantic-validator.v4",
        },
        "model_request": {
            "system_prompt": QUALIFICATION_SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "response_format": qualification_response_format(
                allowed_requirement_ids=requirement_ids,
                allowed_evidence_refs=sorted(allowed_evidence),
            ),
        },
        "candidate_profile": candidate_profile,
        "candidate_evidence": candidate_evidence,
        "job_requirements": job_requirements,
        "approved_alternatives": policies,
        "assessment": validated.model_dump(mode="json"),
        "status_counts": _status_counts(validated.model_dump(mode="json")),
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


def _candidate_input(fixture: dict) -> tuple[dict, list[dict]]:
    data = fixture["resume_data"]
    evidence: list[dict] = []
    profile = {key: [] for key in (
        "skills", "experience", "projects", "education", "certifications", "publications"
    )}
    for section in ("experience", "projects", "education", "certifications", "publications"):
        for index, value in enumerate(data.get(section, []), start=1):
            span_id = f"fixture:{fixture['fixture_id']}:{section}:{index:04d}"
            evidence.append({"span_id": span_id, "section": section, "excerpt": value})
            if section == "experience":
                profile[section].append({"title": "Synthetic fixture experience", "highlights": [value],
                                         "evidence_refs": [span_id]})
            else:
                profile[section].append({"statement": value, "evidence_refs": [span_id]})
    skills = data.get("skills", [])
    if skills:
        span_id = f"fixture:{fixture['fixture_id']}:skills:0001"
        evidence.append({"span_id": span_id, "section": "skills", "excerpt": ", ".join(skills)})
        profile["skills"] = [
            {"observed_name": skill, "canonical_name": skill, "evidence_strength": "claimed",
             "evidence_refs": [span_id]}
            for skill in skills
        ]
    return profile, evidence


def _job_input(requirements: list[dict]) -> tuple[list[dict], list[SimpleNamespace], dict, list[dict]]:
    job_items = []
    validation_items = []
    group_refs = {}
    policies = []
    for item in requirements:
        requirement_id = f"eval_req_{item['local_ref']}"
        groups = item.get("alternative_groups", [])
        group_refs[requirement_id] = frozenset(group["local_ref"] for group in groups)
        policy_ref = item.get("policy_alternative_group")
        job_items.append({
            "requirement_id": requirement_id,
            "statement": item["statement"],
            "importance": item["importance"],
            "scoring_dimension": item["scoring_dimension"],
            "acceptable_evidence_contexts": item["acceptable_evidence_contexts"],
            "minimum_years": item["minimum_years"],
            "alternative_groups": groups,
            "policy_alternative_group": policy_ref,
        })
        validation_items.append(SimpleNamespace(
            requirement_id=requirement_id,
            policy_alternative_group=policy_ref,
        ))
        if policy_ref:
            policy = DEFAULT_REGISTRY.get("alternative_policy", policy_ref)
            policies.append({
                "requirement_id": requirement_id,
                "kind": "approved_policy",
                "policy_ref": policy.version,
                "policy_hash": policy.content_hash,
                "policy": json.loads(canonical_json(policy.content)),
            })
    return job_items, validation_items, group_refs, policies


def _status_counts(artifact: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in artifact["requirement_assessments"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
