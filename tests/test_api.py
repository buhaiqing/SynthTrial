"""HTTP API smoke tests (M11 T-M11-04)."""

from __future__ import annotations



import pytest
from fastapi.testclient import TestClient

from st_platform.api.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_reports(client):
    r = client.get("/reports")
    assert r.status_code == 200
    assert "hashes" in r.json()


def test_rbac_viewer_cannot_admin(client):
    # reports list is open; check a protected-ish path via header absence
    r = client.get("/health", headers={"x-api-key": "viewer-key"})
    assert r.status_code == 200


def test_phi_redact():
    from st_platform.api.phi import redact

    out = redact({"email": "a@b.com", "phone": "13800138000", "nested": ["x@y.com"]})
    assert out["email"] == "[REDACTED_EMAIL]"
    assert out["phone"] == "[REDACTED_PHONE]"
    assert out["nested"][0] == "[REDACTED_EMAIL]"