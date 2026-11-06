"""Password reset: tokens are single-use, expiring, and never reveal accounts."""

import os

os.environ.setdefault("API_KEY", "test-key-for-ci")

import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import notifications
from database import PasswordResetToken, User, get_session, init_db
from main import app, limiter

client = TestClient(app)

EMAIL = "reset-test@patchpilot.dev"
OLD_PW = "oldpassword1"
NEW_PW = "newpassword1"


def _cleanup():
    session = get_session()
    try:
        session.query(User).filter_by(email=EMAIL).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def account(monkeypatch):
    from users import create_user

    init_db()
    limiter.reset()
    _cleanup()
    user = create_user(EMAIL, OLD_PW)
    sent = []
    monkeypatch.setattr(
        notifications,
        "send_password_reset_email",
        lambda to, url: sent.append((to, url)) or True,
    )
    yield {"api_key": user.api_key, "sent": sent}
    _cleanup()


def _token_from(sent) -> str:
    return parse_qs(urlparse(sent[-1][1]).query)["token"][0]


def _insert_token(raw: str, minutes_from_now: int) -> None:
    session = get_session()
    try:
        user = session.query(User).filter_by(email=EMAIL).first()
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                expires_at=now + timedelta(minutes=minutes_from_now),
                created_at=now,
            )
        )
        session.commit()
    finally:
        session.close()


def _forgot(email: str):
    return client.post("/auth/forgot", json={"email": email})


def _reset(token: str, password: str):
    return client.post("/auth/reset", json={"token": token, "password": password})


def _login(password: str):
    return client.post("/auth/login", json={"email": EMAIL, "password": password})


def test_unknown_email_gets_same_answer_and_no_email(account):
    known = _forgot(EMAIL)
    limiter.reset()
    unknown = _forgot("nobody-here@example.com")
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert all(to == EMAIL for to, _ in account["sent"])


def test_known_email_sends_one_link(account):
    assert _forgot(EMAIL).status_code == 200
    assert len(account["sent"]) == 1
    to, url = account["sent"][0]
    assert to == EMAIL
    assert "/reset-password?token=" in url


def test_asking_twice_quickly_sends_only_one_email(account):
    _forgot(EMAIL)
    _forgot(EMAIL)
    assert len(account["sent"]) == 1


def test_full_reset_flow(account):
    _forgot(EMAIL)
    token = _token_from(account["sent"])

    assert _reset(token, NEW_PW).status_code == 200
    assert _login(NEW_PW).status_code == 200
    assert _login(OLD_PW).status_code != 200

    # The old API key was replaced, so old sessions are signed out.
    r = client.get("/patches", headers={"X-API-Key": account["api_key"]})
    assert r.status_code == 401

    # The link works only once.
    assert _reset(token, "anotherpass1").status_code == 400


def test_expired_token_is_rejected():
    _insert_token("expired-token", minutes_from_now=-1)
    assert _reset("expired-token", NEW_PW).status_code == 400


def test_unknown_token_is_rejected():
    assert _reset("not-a-real-token", NEW_PW).status_code == 400


def test_short_password_is_rejected_and_token_survives():
    _insert_token("good-token", minutes_from_now=30)
    assert _reset("good-token", "short").status_code == 400
    assert _reset("good-token", NEW_PW).status_code == 200


def test_account_with_open_token_can_still_be_deleted(account):
    _insert_token("pending-token", minutes_from_now=30)
    r = client.request(
        "DELETE",
        "/me",
        headers={"X-API-Key": account["api_key"]},
        json={"confirm_email": EMAIL},
    )
    assert r.status_code == 200
