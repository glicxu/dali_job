from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from typing import Any

from app.modules.matching_v2.scoring import (
    DeterministicScoreResult,
    GateResult,
    PreferenceScoreItem,
    QualificationScoreItem,
    score_match,
)


FIXTURE_PATH = Path(__file__).with_name("phase5_policy_cases.v1.json")


def evaluate_phase5_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    _validate_fixture(fixture)
    results: dict[str, DeterministicScoreResult] = {}
    case_rows = []
    category_counts: dict[str, Counter[str]] = {}
    reproduction_failures = []
    for case in fixture["cases"]:
        case_input = {**fixture["base_input"], **case.get("input", {})}
        first = _score_case(case_input)
        second = _score_case(case_input)
        first_bytes = _canonical_score(first)
        second_bytes = _canonical_score(second)
        reproduced = first_bytes == second_bytes
        if not reproduced:
            reproduction_failures.append(case["case_id"])
        errors = _expected_errors(first.model_dump(mode="json"), case["expected"])
        passed = reproduced and not errors
        results[case["case_id"]] = first
        counts = category_counts.setdefault(case["category"], Counter())
        counts["total"] += 1
        counts["passed"] += int(passed)
        case_rows.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "passed": passed,
            "reproduced": reproduced,
            "errors": errors,
            "score": first.model_dump(mode="json"),
        })

    ranking_rows = []
    all_pairs_correct = 0
    all_pairs_total = 0
    calibration_errors: list[float] = []
    correlations: list[float] = []
    for ranking in fixture["ranking_sets"]:
        entries = []
        for item in ranking["entries"]:
            score = results[item["case_id"]].overall_score
            if score is None:
                continue
            human_score = float(item["human_score"])
            entries.append({
                "case_id": item["case_id"],
                "predicted_score": score,
                "adjudicated_rank": int(item["adjudicated_rank"]),
                "human_score": human_score,
            })
            calibration_errors.append(float(score) - human_score)
        pairwise_correct, pairwise_total = _pairwise_accuracy(entries)
        correlation = _spearman(entries)
        all_pairs_correct += pairwise_correct
        all_pairs_total += pairwise_total
        if correlation is not None:
            correlations.append(correlation)
        ranking_rows.append({
            "ranking_id": ranking["ranking_id"],
            "adjudication_kind": ranking["adjudication_kind"],
            "ordered_candidates": [
                item["case_id"]
                for item in sorted(entries, key=lambda value: (value["adjudicated_rank"], value["case_id"]))
            ],
            "predicted_order": [
                item["case_id"]
                for item in sorted(entries, key=lambda value: (-value["predicted_score"], value["case_id"]))
            ],
            "ordered_candidate_groups": _ordered_groups(
                entries, value_key="adjudicated_rank", descending=False
            ),
            "predicted_order_groups": _ordered_groups(
                entries, value_key="predicted_score", descending=True
            ),
            "pairwise_correct": pairwise_correct,
            "pairwise_total": pairwise_total,
            "pairwise_accuracy": pairwise_correct / pairwise_total if pairwise_total else None,
            "spearman_rank_correlation": correlation,
        })

    calibration_count = len(calibration_errors)
    mae = (
        sum(abs(value) for value in calibration_errors) / calibration_count
        if calibration_count
        else None
    )
    rmse = (
        math.sqrt(sum(value * value for value in calibration_errors) / calibration_count)
        if calibration_count
        else None
    )
    mean_spearman = sum(correlations) / len(correlations) if correlations else None
    gate = fixture["gates"]
    architecture_gates = {
        "deterministic_reproduction": not reproduction_failures,
        "policy_conformance": all(item["passed"] for item in case_rows),
        "spearman_rank_correlation": (
            mean_spearman is not None
            and mean_spearman >= float(gate["minimum_spearman_rank_correlation"])
        ),
        "pairwise_accuracy": (
            all_pairs_total > 0
            and all_pairs_correct / all_pairs_total >= float(gate["minimum_pairwise_accuracy"])
        ),
        "calibration_mae": mae is not None and mae <= float(gate["maximum_mean_absolute_error"]),
    }
    return {
        "evaluation_type": "phase5_deterministic_scoring",
        "fixture_release": fixture["fixture_release"],
        "scoring_policy_version": "score.v1",
        "case_count": len(case_rows),
        "case_pass_count": sum(item["passed"] for item in case_rows),
        "deterministic_reproduction_failures": reproduction_failures,
        "category_results": {
            key: dict(value) for key, value in sorted(category_counts.items())
        },
        "cases": case_rows,
        "ranking_sets": ranking_rows,
        "ranking_metrics": {
            "ranking_set_count": len(ranking_rows),
            "pairwise_correct": all_pairs_correct,
            "pairwise_total": all_pairs_total,
            "pairwise_accuracy": (
                all_pairs_correct / all_pairs_total if all_pairs_total else None
            ),
            "mean_spearman_rank_correlation": mean_spearman,
        },
        "calibration_metrics": {
            "sample_count": calibration_count,
            "mean_absolute_error": mae,
            "root_mean_squared_error": rmse,
        },
        "architecture_gates": architecture_gates,
        "human_adjudicated_set_count": sum(
            item["adjudication_kind"] == "human_adjudicated" for item in ranking_rows
        ),
        "rollout_decision_eligible": bool(ranking_rows) and all(
            item["adjudication_kind"] == "human_adjudicated" for item in ranking_rows
        ),
        "passed": all(architecture_gates.values()),
    }


def _validate_fixture(fixture: dict[str, Any]) -> None:
    cases = fixture.get("cases", [])
    case_ids = [item.get("case_id") for item in cases]
    if not cases or len(case_ids) != len(set(case_ids)):
        raise ValueError("Phase 5 case IDs must be present and unique.")
    known_cases = set(case_ids)
    allowed_kinds = {"synthetic_architecture_fixture", "human_adjudicated"}
    ranking_ids = []
    for ranking in fixture.get("ranking_sets", []):
        ranking_ids.append(ranking.get("ranking_id"))
        if ranking.get("adjudication_kind") not in allowed_kinds:
            raise ValueError("Ranking sets require a recognized adjudication_kind.")
        reviewer_rankings = ranking.get("reviewer_rankings", [])
        reviewer_refs = [item.get("reviewer_ref") for item in reviewer_rankings]
        if len(reviewer_refs) != len(set(reviewer_refs)):
            raise ValueError("Reviewer references must be unique within a ranking set.")
        if ranking.get("adjudication_kind") == "human_adjudicated" and len(reviewer_rankings) < 2:
            raise ValueError("Human adjudication requires two independent reviewer rankings.")
        for reviewer_ranking in reviewer_rankings:
            reviewer_cases = [
                case_id
                for group in reviewer_ranking.get("ordered_case_groups", [])
                for case_id in group
            ]
            if len(reviewer_cases) < 2 or len(reviewer_cases) != len(set(reviewer_cases)):
                raise ValueError("Each reviewer ranking requires at least two unique cases.")
            if not set(reviewer_cases) <= known_cases:
                raise ValueError("Reviewer ranking refers to an unknown case.")
        entry_cases = [item.get("case_id") for item in ranking.get("entries", [])]
        if len(entry_cases) < 2 or len(entry_cases) != len(set(entry_cases)):
            raise ValueError("Ranking sets require at least two unique cases.")
        if not set(entry_cases) <= known_cases:
            raise ValueError("Ranking set refers to an unknown case.")
        for reviewer_ranking in reviewer_rankings:
            reviewer_cases = {
                case_id
                for group in reviewer_ranking["ordered_case_groups"]
                for case_id in group
            }
            if reviewer_cases != set(entry_cases):
                raise ValueError("Reviewer and adjudicated rankings must cover the same cases.")
        for entry in ranking["entries"]:
            if int(entry["adjudicated_rank"]) < 1:
                raise ValueError("Adjudicated ranks must be positive.")
            if not 0 <= float(entry["human_score"]) <= 100:
                raise ValueError("Human scores must be between 0 and 100.")
    if len(ranking_ids) != len(set(ranking_ids)):
        raise ValueError("Ranking IDs must be unique.")


def _score_case(payload: dict[str, Any]) -> DeterministicScoreResult:
    return score_match(
        role_family=payload["role_family"],
        track=payload["track"],
        target_level=payload["target_level"],
        level_confidence=float(payload["level_confidence"]),
        qualification_items=[
            QualificationScoreItem.model_validate(item)
            for item in payload["qualification_items"]
        ],
        preference_items=[
            PreferenceScoreItem.model_validate(item)
            for item in payload.get("preference_items", [])
        ],
        gates=[GateResult.model_validate(item) for item in payload.get("gates", [])],
    )


def _canonical_score(result: DeterministicScoreResult) -> bytes:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _expected_errors(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors = []
    for key, value in expected.items():
        if key == "reason_codes_include":
            missing = sorted(set(value) - set(actual["reason_codes"]))
            if missing:
                errors.append(f"reason_codes missing {missing}")
        elif actual.get(key) != value:
            errors.append(f"{key}: expected {value!r}, observed {actual.get(key)!r}")
    return errors


def _pairwise_accuracy(entries: list[dict[str, Any]]) -> tuple[int, int]:
    correct = 0
    total = 0
    for left_index, left in enumerate(entries):
        for right in entries[left_index + 1:]:
            if left["adjudicated_rank"] == right["adjudicated_rank"]:
                continue
            total += 1
            human_order = left["adjudicated_rank"] < right["adjudicated_rank"]
            if left["predicted_score"] != right["predicted_score"]:
                predicted_order = left["predicted_score"] > right["predicted_score"]
                correct += int(human_order == predicted_order)
    return correct, total


def _ordered_groups(
    entries: list[dict[str, Any]],
    *,
    value_key: str,
    descending: bool,
) -> list[list[str]]:
    grouped: dict[float, list[str]] = {}
    for entry in entries:
        grouped.setdefault(float(entry[value_key]), []).append(str(entry["case_id"]))
    return [
        sorted(grouped[value])
        for value in sorted(grouped, reverse=descending)
    ]


def _spearman(entries: list[dict[str, Any]]) -> float | None:
    if len(entries) < 2:
        return None
    predicted = _rank_descending([float(item["predicted_score"]) for item in entries])
    adjudicated = [float(item["adjudicated_rank"]) for item in entries]
    return _pearson(predicted, adjudicated, invert_right=False)


def _rank_descending(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (-item[1], item[0]))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2
        for index in range(cursor, end):
            ranks[ordered[index][0]] = average_rank
        cursor = end
    return ranks


def _pearson(left: list[float], right: list[float], *, invert_right: bool) -> float | None:
    adjusted_right = [-value for value in right] if invert_right else right
    left_mean = sum(left) / len(left)
    right_mean = sum(adjusted_right) / len(adjusted_right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, adjusted_right, strict=True)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in adjusted_right)
    denominator = math.sqrt(left_variance * right_variance)
    return numerator / denominator if denominator else None
