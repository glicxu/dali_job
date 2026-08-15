from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.modules.accounts.models import User, Workspace
from app.modules.automation.entitlements import (
    EntitlementCatalog,
    EntitlementConfigurationError,
    TierEntitlement,
    load_entitlement_catalog,
)
from app.modules.automation.models import UsageLedger, UserSubscription
from app.modules.automation.repository import (
    InvalidUsageTransition,
    QuotaExceeded,
    consume_reservation,
    ensure_free_subscription,
    release_reservation,
    reserve_provider_search,
    usage_summary,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _catalog(*, free_searches: int = 2, version: str = "test-v1") -> EntitlementCatalog:
    return EntitlementCatalog(
        version=version,
        tiers={
            "free": TierEntitlement(free_searches, 1, 10_080),
            "starter": TierEntitlement(30, 3, 1_440),
            "plus": TierEntitlement(90, 10, 480),
        },
    )


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        yield session


def _account(db: Session) -> tuple[User, Workspace]:
    user = User(email="mobile@example.com", display_name="Mobile User")
    db.add(user)
    db.flush()
    workspace = Workspace(owner_user_id=user.id, name="Mobile User's Career Search")
    db.add(workspace)
    db.flush()
    return user, workspace


def test_default_entitlements_use_approved_weekly_search_allowances() -> None:
    catalog = load_entitlement_catalog("", version="weekly-v1")

    assert catalog.for_tier("free").searches_per_period == 1
    assert catalog.for_tier("starter").searches_per_period == 3
    assert catalog.for_tier("plus").searches_per_period == 5
    assert catalog.for_tier("super").searches_per_period is None
    assert catalog.for_tier("super").minimum_interval_minutes == 1


def test_entitlement_json_must_define_every_supported_tier() -> None:
    with pytest.raises(EntitlementConfigurationError):
        load_entitlement_catalog(
            '{"free":{"searches_per_period":4,"maximum_active_criteria":1,'
            '"minimum_interval_minutes":10080}}',
            version="invalid",
        )


def test_entitlement_json_loads_validated_values() -> None:
    catalog = load_entitlement_catalog(
        """
        {
          "free": {"searches_per_period": 4, "maximum_active_criteria": 1, "minimum_interval_minutes": 10080},
          "starter": {"searches_per_period": 30, "maximum_active_criteria": 3, "minimum_interval_minutes": 1440},
          "plus": {"searches_per_period": 90, "maximum_active_criteria": 10, "minimum_interval_minutes": 480}
        }
        """,
        version="approved-v1",
    )

    assert catalog.version == "approved-v1"
    assert catalog.for_tier("starter").searches_per_period == 30
    assert catalog.for_tier("plus").minimum_interval_minutes == 480
    assert catalog.for_tier("super").searches_per_period is None


def test_ensure_free_subscription_is_idempotent(db: Session) -> None:
    user, workspace = _account(db)

    first = ensure_free_subscription(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        catalog=_catalog(),
        now=NOW,
    )
    second = ensure_free_subscription(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        catalog=_catalog(),
        now=NOW + timedelta(hours=1),
    )

    assert first.id == second.id
    assert first.tier_code == "free"
    assert first.period_started_at == NOW
    assert first.period_ends_at == NOW + timedelta(days=7)
    assert len(db.scalars(select(UserSubscription)).all()) == 1


def test_reservations_are_idempotent_and_enforce_allowance(db: Session) -> None:
    user, workspace = _account(db)
    catalog = _catalog(free_searches=2)
    ensure_free_subscription(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        catalog=catalog,
        now=NOW,
    )

    first, first_created = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="scheduled-run-1",
        catalog=catalog,
        now=NOW,
    )
    replay, replay_created = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="scheduled-run-1",
        catalog=catalog,
        now=NOW,
    )
    second, second_created = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="scheduled-run-2",
        catalog=catalog,
        now=NOW,
    )

    assert first_created is True
    assert replay_created is False
    assert replay.id == first.id
    assert second_created is True
    with pytest.raises(QuotaExceeded) as exc_info:
        reserve_provider_search(
            db,
            user_id=user.id,
            idempotency_key="scheduled-run-3",
            catalog=catalog,
            now=NOW,
        )
    assert exc_info.value.allowance == 2
    assert exc_info.value.used == 2

    release_reservation(db, ledger_id=second.id, reason="provider was not called", now=NOW)
    third, third_created = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="scheduled-run-3",
        catalog=catalog,
        now=NOW,
    )
    assert third_created is True
    assert third.state == "reserved"


def test_usage_transitions_and_summary_are_idempotent(db: Session) -> None:
    user, workspace = _account(db)
    catalog = _catalog(free_searches=3)
    ensure_free_subscription(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        catalog=catalog,
        now=NOW,
    )
    first, _ = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="run-consumed",
        catalog=catalog,
        now=NOW,
    )
    second, _ = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="run-released",
        catalog=catalog,
        now=NOW,
    )

    consume_reservation(db, ledger_id=first.id, now=NOW + timedelta(minutes=1))
    consume_reservation(db, ledger_id=first.id, now=NOW + timedelta(minutes=2))
    release_reservation(db, ledger_id=second.id, now=NOW + timedelta(minutes=1))
    release_reservation(db, ledger_id=second.id, now=NOW + timedelta(minutes=2))

    with pytest.raises(InvalidUsageTransition):
        release_reservation(db, ledger_id=first.id, now=NOW + timedelta(minutes=3))
    with pytest.raises(InvalidUsageTransition):
        consume_reservation(db, ledger_id=second.id, now=NOW + timedelta(minutes=3))

    summary = usage_summary(db, user_id=user.id, catalog=catalog, now=NOW)
    assert summary.consumed == 1
    assert summary.reserved == 0
    assert summary.available == 2


def test_new_period_excludes_prior_usage(db: Session) -> None:
    user, workspace = _account(db)
    catalog = _catalog(free_searches=1)
    subscription = ensure_free_subscription(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        catalog=catalog,
        now=NOW,
    )
    prior, _ = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="prior-period",
        catalog=catalog,
        now=NOW,
    )
    consume_reservation(db, ledger_id=prior.id, now=NOW)

    next_period = NOW + timedelta(days=8)
    current, created = reserve_provider_search(
        db,
        user_id=user.id,
        idempotency_key="current-period",
        catalog=catalog,
        now=next_period,
    )

    assert created is True
    assert current.state == "reserved"
    assert subscription.period_started_at == NOW + timedelta(days=7)
    assert subscription.period_ends_at == NOW + timedelta(days=14)
    assert len(db.scalars(select(UsageLedger)).all()) == 2


def test_super_subscription_has_unlimited_provider_searches(db: Session) -> None:
    user, workspace = _account(db)
    catalog = load_entitlement_catalog("", version="internal-test-v1")
    subscription = ensure_free_subscription(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        catalog=catalog,
        now=NOW,
    )
    subscription.tier_code = "super"
    db.flush()

    for index in range(20):
        ledger, created = reserve_provider_search(
            db,
            user_id=user.id,
            idempotency_key=f"super-run-{index}",
            catalog=catalog,
            now=NOW,
        )
        assert created is True
        assert ledger.allowance_snapshot == -1

    summary = usage_summary(db, user_id=user.id, catalog=catalog, now=NOW)
    assert summary.allowance is None
    assert summary.available is None
    assert summary.reserved == 20
