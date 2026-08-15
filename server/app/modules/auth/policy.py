from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.modules.auth.dependencies import get_current_identity

PUBLIC_API_ROUTES = {
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/verify-email"),
    ("POST", "/auth/resend-verification"),
    ("POST", "/auth/forgot-password"),
    ("POST", "/auth/reset-password"),
    ("POST", "/auth/mobile/sessions"),
    ("POST", "/auth/mobile/sessions/refresh"),
    ("GET", "/health"),
    ("GET", "/health/db"),
    ("GET", "/documents/downloads/{token}"),
    ("POST", "/guest-trials"),
}


def _has_identity_dependency(dependant: Dependant) -> bool:
    for dependency in dependant.dependencies:
        if dependency.call is get_current_identity or _has_identity_dependency(dependency):
            return True
    return False


def _has_guest_dependency(dependant: Dependant) -> bool:
    from app.modules.guest_trials.dependencies import get_current_guest_trial

    for dependency in dependant.dependencies:
        if dependency.call is get_current_guest_trial or _has_guest_dependency(dependency):
            return True
    return False


def validate_route_authorization(routers: Iterable[APIRouter]) -> None:
    unprotected: list[str] = []
    for router in routers:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                route_key = (method, route.path)
                if route_key in PUBLIC_API_ROUTES:
                    continue
                if not _has_identity_dependency(route.dependant) and not _has_guest_dependency(route.dependant):
                    unprotected.append(f"{method} /api/v1{route.path}")
    if unprotected:
        routes = ", ".join(sorted(unprotected))
        raise RuntimeError(f"Non-public API routes are missing authentication dependencies: {routes}")
