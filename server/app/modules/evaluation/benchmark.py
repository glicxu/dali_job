from __future__ import annotations

from collections import Counter

from app.modules.evaluation.models import EvaluationJobSnapshot

PILOT_COVERAGE_SLOTS = (
    {"code": "software_backend", "label": "Backend or distributed-systems engineer"},
    {"code": "software_infrastructure", "label": "Infrastructure, cloud, or site-reliability engineer"},
    {"code": "software_mobile", "label": "Mobile or client-platform engineer"},
    {"code": "ml_data", "label": "Machine-learning or data-platform engineer"},
    {"code": "hardware_design", "label": "Silicon, electrical, or hardware-design engineer"},
    {"code": "embedded_firmware", "label": "Embedded-systems or firmware engineer"},
    {"code": "product_management", "label": "Product Manager"},
    {"code": "technical_program", "label": "Technical Program Manager"},
    {"code": "engineering_management", "label": "Engineering Manager"},
    {"code": "principal_architecture", "label": "Principal engineer, architect, or technical leader"},
)


def build_admission_report(
    snapshots: list[EvaluationJobSnapshot],
    *,
    benchmark_release: str,
) -> dict:
    release_snapshots = [item for item in snapshots if item.benchmark_release == benchmark_release]
    accepted = [item for item in release_snapshots if item.review_status == "accepted"]
    drafts = [item for item in release_snapshots if item.review_status == "draft"]
    rejected = [item for item in release_snapshots if item.review_status == "rejected"]
    accepted_by_slot: dict[str, list[EvaluationJobSnapshot]] = {}
    for snapshot in accepted:
        accepted_by_slot.setdefault(snapshot.coverage_slot, []).append(snapshot)
    slot_rows = [{
        **slot,
        "status": "filled" if accepted_by_slot.get(slot["code"]) else (
            "awaiting_review" if any(item.coverage_slot == slot["code"] for item in drafts) else "missing"
        ),
        "accepted_snapshot_ids": [item.public_id for item in accepted_by_slot.get(slot["code"], [])],
    } for slot in PILOT_COVERAGE_SLOTS]
    employer_counts = Counter((item.company.strip() or "Unknown") for item in accepted)
    violations = []
    if len(employer_counts) < 4 and len(accepted) >= 4:
        violations.append("fewer_than_four_employers")
    for employer, count in sorted(employer_counts.items()):
        if count > 2:
            violations.append(f"employer_limit_exceeded:{employer}:{count}")
    duplicate_slots = sorted(slot for slot, items in accepted_by_slot.items() if len(items) > 1)
    violations.extend(f"coverage_slot_duplicate:{slot}" for slot in duplicate_slots)
    missing = [row["code"] for row in slot_rows if row["status"] == "missing"]
    awaiting = [row["code"] for row in slot_rows if row["status"] == "awaiting_review"]
    return {
        "benchmark_release": benchmark_release,
        "ready": not missing and not awaiting and not violations,
        "slots": slot_rows,
        "missing_slots": missing,
        "awaiting_review_slots": awaiting,
        "accepted_count": len(accepted),
        "draft_count": len(drafts),
        "rejected_count": len(rejected),
        "employer_counts": dict(sorted(employer_counts.items())),
        "balance_violations": violations,
        "storage_policy": "deferred_internal_testing",
    }
