from __future__ import annotations

import json
import os
from dataclasses import dataclass


TIER_CODES = ("free", "starter", "plus")
ENTITLEMENTS_ENV_VAR = "DALIJOB_TIER_ENTITLEMENTS_JSON"
ENTITLEMENT_VERSION_ENV_VAR = "DALIJOB_TIER_ENTITLEMENT_VERSION"
DEFAULT_ENTITLEMENT_VERSION = "weekly-searches-v1-2026-08-14"


class EntitlementConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class TierEntitlement:
    searches_per_period: int
    maximum_active_criteria: int
    minimum_interval_minutes: int

    def __post_init__(self) -> None:
        if self.searches_per_period < 0:
            raise EntitlementConfigurationError("searches_per_period cannot be negative")
        if self.maximum_active_criteria < 0:
            raise EntitlementConfigurationError("maximum_active_criteria cannot be negative")
        if self.minimum_interval_minutes < 1:
            raise EntitlementConfigurationError("minimum_interval_minutes must be positive")


@dataclass(frozen=True)
class EntitlementCatalog:
    version: str
    tiers: dict[str, TierEntitlement]

    def __post_init__(self) -> None:
        if not self.version.strip() or len(self.version) > 64:
            raise EntitlementConfigurationError("entitlement version must contain 1 to 64 characters")
        missing = set(TIER_CODES) - set(self.tiers)
        extra = set(self.tiers) - set(TIER_CODES)
        if missing or extra:
            raise EntitlementConfigurationError(
                f"entitlements must define exactly {', '.join(TIER_CODES)}"
            )

    def for_tier(self, tier_code: str) -> TierEntitlement:
        try:
            return self.tiers[tier_code]
        except KeyError as exc:
            raise EntitlementConfigurationError(f"unknown tier: {tier_code}") from exc


# Approved weekly automated-search allowances. Deployments can still override
# the versioned catalog through DALIJOB_TIER_ENTITLEMENTS_JSON.
DEFAULT_ENTITLEMENTS = {
    "free": TierEntitlement(1, 1, 7 * 24 * 60),
    "starter": TierEntitlement(3, 3, 24 * 60),
    "plus": TierEntitlement(5, 10, 8 * 60),
}


def load_entitlement_catalog(
    raw_json: str | None = None,
    *,
    version: str | None = None,
) -> EntitlementCatalog:
    configured = raw_json if raw_json is not None else os.getenv(ENTITLEMENTS_ENV_VAR, "").strip()
    resolved_version = (
        version
        if version is not None
        else os.getenv(ENTITLEMENT_VERSION_ENV_VAR, "").strip() or DEFAULT_ENTITLEMENT_VERSION
    )
    if not configured:
        return EntitlementCatalog(version=resolved_version, tiers=dict(DEFAULT_ENTITLEMENTS))

    try:
        payload = json.loads(configured)
    except json.JSONDecodeError as exc:
        raise EntitlementConfigurationError("tier entitlements must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise EntitlementConfigurationError("tier entitlements must be a JSON object")

    tiers: dict[str, TierEntitlement] = {}
    for tier_code, value in payload.items():
        if not isinstance(value, dict):
            raise EntitlementConfigurationError(f"{tier_code} entitlement must be an object")
        expected = {
            "searches_per_period",
            "maximum_active_criteria",
            "minimum_interval_minutes",
        }
        if set(value) != expected:
            raise EntitlementConfigurationError(
                f"{tier_code} entitlement must define exactly {', '.join(sorted(expected))}"
            )
        if any(type(value[key]) is not int for key in expected):
            raise EntitlementConfigurationError(
                f"{tier_code} entitlement values must be integers"
            )
        tiers[str(tier_code)] = TierEntitlement(
            searches_per_period=value["searches_per_period"],
            maximum_active_criteria=value["maximum_active_criteria"],
            minimum_interval_minutes=value["minimum_interval_minutes"],
        )
    return EntitlementCatalog(version=resolved_version, tiers=tiers)
