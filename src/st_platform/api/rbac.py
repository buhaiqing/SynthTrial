"""RBAC for SynthTrial HTTP API (M11 T-M11-06)."""

from __future__ import annotations

from enum import Enum
from collections.abc import Callable

from fastapi import HTTPException, Request


class Role(str, Enum):
    VIEWER = "viewer"
    REVIEWER = "reviewer"
    ADMIN = "admin"


_ROLE_RANK = {Role.VIEWER: 0, Role.REVIEWER: 1, Role.ADMIN: 2}

# Dev mapping: API key -> role. Production swaps to Entra ID claims.
_API_KEYS: dict[str, Role] = {
    "viewer-key": Role.VIEWER,
    "reviewer-key": Role.REVIEWER,
    "admin-key": Role.ADMIN,
}


def role_of(request: Request) -> Role:
    key = request.headers.get("x-api-key", "")
    if key not in _API_KEYS:
        raise HTTPException(status_code=401, detail="invalid or missing api key")
    return _API_KEYS[key]


def require_role(*roles: Role) -> Callable:
    minimum = min((_ROLE_RANK[r] for r in roles), default=0)

    def dep(request: Request) -> Role:
        r = role_of(request)
        if _ROLE_RANK[r] < minimum:
            raise HTTPException(status_code=403, detail="insufficient role")
        return r

    return dep