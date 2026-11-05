"""Registration is gated by a server-side invite code from INVITE_CODES."""

import os

os.environ.setdefault("API_KEY", "test-key-for-ci")

import pytest
from fastapi.testclient import TestClient

from database import User, get_session, init_db
from main import app, limiter

client = TestClient(app)

EMAIL_PREFIX = "invite-test-"


def _cleanup():
    session = get_session()
    try:
        session.query(User).filter(User.email.like(f"{EMAIL_PREFIX}%")).delete(
            synchronize_session=False
        )
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean_state():
    init_db()
    limiter.reset()  # register is limited to 5/minute
    _cleanup()
    yield
    _cleanup()


def _register(email: str, code):
    body = {"email": f"{EMAIL_PREFIX}{email}@patchpilot.dev", "password": "testpass123"}
    if code is not None:
        body["invite_code"] = code
    return client.post("/auth/register", json=body)


def test_missing_code_is_rejected(monkeypatch):
    monkeypatch.setenv("INVITE_CODES", "code-one,code-two")
    assert _register("a", None).status_code == 403


def test_empty_code_is_rejected(monkeypatch):
    monkeypatch.setenv("INVITE_CODES", "code-one,code-two")
    assert _register("a", "").status_code == 403


def test_wrong_code_is_rejected(monkeypatch):
    monkeypatch.setenv("INVITE_CODES", "code-one,code-two")
    assert _register("a", "nope").status_code == 403


def test_old_hardcoded_code_no_longer_works(monkeypatch):
    monkeypatch.setenv("INVITE_CODES", "code-one,code-two")
    assert _register("a", "PATCHPILOT2026").status_code == 403


def test_valid_codes_work_and_spaces_are_ignored(monkeypatch):
    monkeypatch.setenv("INVITE_CODES", "code-one, code-two")
    r1 = _register("a", "code-one")
    r2 = _register("b", "  code-two ")
    assert r1.status_code == 201 and "api_key" in r1.json()
    assert r2.status_code == 201


def test_closed_when_no_codes_configured(monkeypatch):
    monkeypatch.delenv("INVITE_CODES", raising=False)
    assert _register("a", "anything").status_code == 403
    monkeypatch.setenv("INVITE_CODES", "")
    assert _register("a", "").status_code == 403
