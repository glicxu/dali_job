from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.matching_v2.models import CandidateCareerProfile, JobFamilyPreMatch
from app.modules.matching_v2.pre_match import (
    create_matching_intent,
    create_or_get_job_family_pre_match,
    get_matching_intent,
)
from test_matching_v2_qualification import _foundation


def test_job_family_pre_match_honors_intent_instead_of_primary_profile() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        owner, candidate, job = _foundation(db)
        intent = create_matching_intent(
            db,
            owner=owner,
            candidate_profile=candidate,
            expected_revision=0,
            target_role_text="Senior Software Engineer",
            job_family="software_engineering",
            track="individual_contributor",
            target_level="senior",
            selected_candidate_career_profile_id=None,
            source="user_preferred",
        )

        first = create_or_get_job_family_pre_match(
            db, owner=owner, candidate_profile=candidate, intent=intent, job_profile=job
        )
        repeated = create_or_get_job_family_pre_match(
            db, owner=owner, candidate_profile=candidate, intent=intent, job_profile=job
        )
        selected = db.get(CandidateCareerProfile, first.selected_candidate_career_profile_id)

        assert repeated.id == first.id
        assert selected is not None
        assert selected.role_family == "software_engineering"
        assert first.family_compatibility == "exact"
        assert first.track_compatibility == "exact"
        assert first.level_compatibility == "within_range"
        assert first.proceed_to_detailed_match is True
        assert db.scalar(select(JobFamilyPreMatch).where(JobFamilyPreMatch.id == first.id)) is first


def test_matching_intent_revisions_are_exactly_addressable() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        owner, candidate, _ = _foundation(db)
        first = create_matching_intent(
            db,
            owner=owner,
            candidate_profile=candidate,
            expected_revision=0,
            target_role_text="Software Engineer",
            job_family="software_engineering",
            track="individual_contributor",
            target_level="senior",
            selected_candidate_career_profile_id=None,
            source="resume_derived",
        )
        second = create_matching_intent(
            db,
            owner=owner,
            candidate_profile=candidate,
            public_id=first.public_id,
            expected_revision=1,
            target_role_text="Staff Software Engineer",
            job_family="software_engineering",
            track="individual_contributor",
            target_level="staff",
            selected_candidate_career_profile_id=None,
            source="user_confirmed",
        )

        assert get_matching_intent(db, owner=owner, public_id=first.public_id).revision == 2
        assert get_matching_intent(db, owner=owner, public_id=first.public_id, revision=1).target_level == "senior"
        assert second.revision == 2
