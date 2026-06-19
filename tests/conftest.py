"""
Shared test fixtures.

Every test runs against a freshly-built app with an isolated temp data dir, the
extractive stub (no network), auth and rate limiting off by default. Auth and
rate-limit behaviour are exercised in their own tests with purpose-built apps.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_settings(tmp_path, **overrides) -> Settings:
    base = dict(
        data_dir=str(tmp_path),
        llm_force_stub=True,
        require_auth=False,
        rate_limit_enabled=False,
        log_json=False,
        log_level="WARNING",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_client(client):
    """A client pre-loaded with three small documents in namespace 'corp'."""
    docs = {
        "policy.txt": b"All full-time employees receive 20 days of paid annual leave each year. "
                      b"Remote work is allowed up to three days per week with manager approval.",
        "faq.md": b"# Support FAQ\nTo reset your password, open account settings and click Reset password. "
                  b"Refunds are processed within 14 business days.",
        "team.csv": b"name,role,location\nAda Lovelace,Engineer,Oakville\nGrace Hopper,Architect,Toronto",
    }
    for fn, data in docs.items():
        r = client.post("/v1/documents?namespace=corp", files={"file": (fn, data)})
        assert r.status_code == 201, r.text
    return client
