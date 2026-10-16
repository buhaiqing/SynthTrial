"""RBAC unit tests (M11 T-M11-06)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from st_platform.api.rbac import Role, require_role, role_of


def _request(key: str | None = None):
    scope = {"type": "http", "headers": []}
    if key is not None:
        scope["headers"] = [(b"x-api-key", key.encode())]
    return Request(scope)


def test_invalid_key_401():
    with pytest.raises(HTTPException) as exc:
        role_of(_request())
    assert exc.value.status_code == 401


def test_viewer_blocked_from_admin():
    dep = require_role(Role.ADMIN)
    with pytest.raises(HTTPException) as exc:
        dep(_request("viewer-key"))
    assert exc.value.status_code == 403


def test_admin_allowed():
    dep = require_role(Role.ADMIN)
    assert dep(_request("admin-key")) == Role.ADMIN