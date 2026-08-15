from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.automation.entitlements import EntitlementCatalog, load_entitlement_catalog
from app.modules.automation.models import UsageLedger, UserSubscription


USAGE_TYPE_PROVIDER_SEARCH = "provider_search"
ACTIVE_USAGE_STATES = ("reserved", "consumed")
PERIOD_LENGTH = timedelta(days=7)


class SubscriptionUnavailable(RuntimeError):
    pass


class QuotaExceeded(RuntimeError):
    def __init__(self, *, allowance: int, used: int, requested: int) -> None:
        super().__init__(
            f"provider search allowance exceeded: {used} used or reserved, "
            f"{requested} requested, {allowance} allowed"
        )
        self.allowance = allowance
        self.used = used
        self.requested = requested


class InvalidUsageTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class UsageSummary:
    tier_code: str
    entitlement_version: str
    period_started_at: datetime
    period_ends_at: datetime
    allowance: int | None
    reserved: int
    consumed: int

    @property
    def available(self) -> int | None:
        if self.allowance is None:
            return None
        return max(self.allowance - self.reserved - self.consumed, 0)


def ensure_free_subscription(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    catalog: EntitlementCatalog | None = None,
    now: datetime | None = None,
) -> UserSubscription:
    subscription = db.scalar(
        select(UserSubscription).where(UserSubscription.user_id == user_id).limit(1)
    )
    if subscription is not None:
        return subscription

    current = _utc(now or datetime.now(timezone.utc))
    resolved_catalog = catalog or load_entitlement_catalog()
    subscription = UserSubscription(
        workspace_id=workspace_id,
        user_id=user_id,
        tier_code="free",
        status="active",
        entitlement_version=resolved_catalog.version,
        period_started_at=current,
        period_ends_at=current + PERIOD_LENGTH,
    )
    db.add(subscription)
    db.flush()
    return subscription


def reserve_provider_search(
    db: Session,
    *,
    user_id: int,
    idempotency_key: str,
    units: int = 1,
    reason: str | None = None,
    catalog: EntitlementCatalog | None = None,
    now: datetime | None = None,
) -> tuple[UsageLedger, bool]:
    if not idempotency_key or len(idempotency_key) > 64:
        raise ValueError("idempotency_key must contain 1 to 64 characters")
    if units < 1:
        raise ValueError("units must be positive")

    subscription = db.scalar(
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id)
        .with_for_update()
    )
    if subscription is None or subscription.deleted_at is not None:
        raise SubscriptionUnavailable("user has no active subscription")
    if subscription.status != "active":
        raise SubscriptionUnavailable(f"subscription is {subscription.status}")

    current = _utc(now or datetime.now(timezone.utc))
    _advance_period(subscription, current)

    existing = db.scalar(
        select(UsageLedger).where(
            UsageLedger.user_id == user_id,
            UsageLedger.usage_type == USAGE_TYPE_PROVIDER_SEARCH,
            UsageLedger.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False

    resolved_catalog = catalog or load_entitlement_catalog()
    entitlement = resolved_catalog.for_tier(subscription.tier_code)
    subscription.entitlement_version = resolved_catalog.version
    used = _active_usage_total(db, subscription, current)
    if entitlement.searches_per_period is not None and used + units > entitlement.searches_per_period:
        raise QuotaExceeded(
            allowance=entitlement.searches_per_period,
            used=used,
            requested=units,
        )

    ledger = UsageLedger(
        workspace_id=subscription.workspace_id,
        user_id=user_id,
        subscription_id=subscription.id,
        usage_type=USAGE_TYPE_PROVIDER_SEARCH,
        units=units,
        state="reserved",
        idempotency_key=idempotency_key,
        entitlement_version=resolved_catalog.version,
        tier_code_snapshot=subscription.tier_code,
        allowance_snapshot=entitlement.searches_per_period if entitlement.searches_per_period is not None else -1,
        reason=reason,
        reserved_at=current,
    )
    db.add(ledger)
    db.flush()
    return ledger, True


def consume_reservation(
    db: Session,
    *,
    ledger_id: int,
    now: datetime | None = None,
) -> UsageLedger:
    ledger = _locked_ledger(db, ledger_id)
    if ledger.state == "consumed":
        return ledger
    if ledger.state != "reserved":
        raise InvalidUsageTransition(f"cannot consume usage in state {ledger.state}")
    ledger.state = "consumed"
    ledger.consumed_at = _utc(now or datetime.now(timezone.utc))
    db.flush()
    return ledger


def release_reservation(
    db: Session,
    *,
    ledger_id: int,
    reason: str | None = None,
    now: datetime | None = None,
) -> UsageLedger:
    ledger = _locked_ledger(db, ledger_id)
    if ledger.state == "released":
        return ledger
    if ledger.state != "reserved":
        raise InvalidUsageTransition(f"cannot release usage in state {ledger.state}")
    ledger.state = "released"
    ledger.released_at = _utc(now or datetime.now(timezone.utc))
    if reason:
        ledger.reason = reason
    db.flush()
    return ledger


def usage_summary(
    db: Session,
    *,
    user_id: int,
    catalog: EntitlementCatalog | None = None,
    now: datetime | None = None,
) -> UsageSummary:
    subscription = db.scalar(
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id)
        .with_for_update()
    )
    if subscription is None or subscription.deleted_at is not None:
        raise SubscriptionUnavailable("user has no active subscription")
    if subscription.status != "active":
        raise SubscriptionUnavailable(f"subscription is {subscription.status}")
    current = _utc(now or datetime.now(timezone.utc))
    _advance_period(subscription, current)
    resolved_catalog = catalog or load_entitlement_catalog()
    entitlement = resolved_catalog.for_tier(subscription.tier_code)
    reserved, consumed = _usage_totals_by_state(db, subscription)
    return UsageSummary(
        tier_code=subscription.tier_code,
        entitlement_version=resolved_catalog.version,
        period_started_at=_utc(subscription.period_started_at),
        period_ends_at=_utc(subscription.period_ends_at),
        allowance=entitlement.searches_per_period,
        reserved=reserved,
        consumed=consumed,
    )


def _locked_ledger(db: Session, ledger_id: int) -> UsageLedger:
    ledger = db.scalar(
        select(UsageLedger).where(UsageLedger.id == ledger_id).with_for_update()
    )
    if ledger is None:
        raise LookupError("usage ledger entry not found")
    return ledger


def _advance_period(subscription: UserSubscription, current: datetime) -> None:
    period_start = _utc(subscription.period_started_at)
    period_end = _utc(subscription.period_ends_at)
    expected_end = period_start + PERIOD_LENGTH
    if period_end != expected_end:
        period_end = expected_end
    if period_end > current:
        subscription.period_ends_at = period_end
        return
    if period_end <= period_start:
        period_end = period_start + PERIOD_LENGTH
    while period_end <= current:
        period_start = period_end
        period_end = period_start + PERIOD_LENGTH
    subscription.period_started_at = period_start
    subscription.period_ends_at = period_end


def _active_usage_total(db: Session, subscription: UserSubscription, current: datetime) -> int:
    if current >= _utc(subscription.period_ends_at):
        return 0
    return int(
        db.scalar(
            select(func.coalesce(func.sum(UsageLedger.units), 0)).where(
                UsageLedger.subscription_id == subscription.id,
                UsageLedger.state.in_(ACTIVE_USAGE_STATES),
                UsageLedger.reserved_at >= subscription.period_started_at,
                UsageLedger.reserved_at < subscription.period_ends_at,
            )
        )
        or 0
    )


def _usage_totals_by_state(
    db: Session,
    subscription: UserSubscription,
) -> tuple[int, int]:
    rows = db.execute(
        select(UsageLedger.state, func.coalesce(func.sum(UsageLedger.units), 0))
        .where(
            UsageLedger.subscription_id == subscription.id,
            UsageLedger.state.in_(ACTIVE_USAGE_STATES),
            UsageLedger.reserved_at >= subscription.period_started_at,
            UsageLedger.reserved_at < subscription.period_ends_at,
        )
        .group_by(UsageLedger.state)
    ).all()
    totals = {state: int(units) for state, units in rows}
    return totals.get("reserved", 0), totals.get("consumed", 0)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
