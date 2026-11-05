"""Data isolation: one user must never see another user's patches or activity."""

import os

os.environ.setdefault("API_KEY", "test-key-for-ci")

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from database import ActivityLog, Patch, Repo, User, get_session, init_db
from main import app

client = TestClient(app)

PATCH_MARKER = "isolation_test_a.py"
ACTIVITY_MARKER = "isolation-test-activity-user-a"

EMAIL_A = "isolation-a@patchpilot.dev"
EMAIL_B = "isolation-b@patchpilot.dev"
EMAIL_ADMIN = "isolation-admin@patchpilot.dev"


def _get_or_create_user(email: str, admin: bool = False) -> tuple[int, str]:
    from users import create_user

    session = get_session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user:
            create_user(email, "testpass123")
            user = session.query(User).filter_by(email=email).first()
        if admin and not user.is_admin:
            user.is_admin = True
            session.commit()
        return user.id, user.api_key
    finally:
        session.close()


def _get_or_create_snapshot(session) -> tuple[int, bool]:
    """Patches need a snapshot row. Reuse one, or build a minimal one."""
    from database import ChangelogSnapshot

    existing = session.query(ChangelogSnapshot).first()
    if existing:
        return existing.id, False

    values = {}
    for col in ChangelogSnapshot.__table__.columns:
        if col.primary_key or col.nullable:
            continue
        if col.default is not None or col.server_default is not None:
            continue
        py_type = col.type.python_type
        if py_type is bool:
            values[col.name] = False
        elif py_type is int:
            values[col.name] = 0
        elif py_type is datetime:
            values[col.name] = datetime.now(tz=UTC)
        else:
            values[col.name] = "isolation-test"
    snap = ChangelogSnapshot(**values)
    session.add(snap)
    session.commit()
    return snap.id, True


@pytest.fixture(scope="module")
def world():
    init_db()
    user_a_id, key_a = _get_or_create_user(EMAIL_A)
    _, key_b = _get_or_create_user(EMAIL_B)
    _, key_admin = _get_or_create_user(EMAIL_ADMIN, admin=True)

    session = get_session()
    repo_id = None
    snapshot_id = None
    snapshot_created = False
    try:
        snapshot_id, snapshot_created = _get_or_create_snapshot(session)

        repo = Repo(
            user_id=user_a_id,
            github_url="https://github.com/isolation-test/repo-a",
            owner="isolation-test",
            repo_name="repo-a",
            api_name="stripe",
        )
        session.add(repo)
        session.commit()
        repo_id = repo.id

        session.add(
            Patch(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_path=PATCH_MARKER,
                original_code="old",
                patched_code="new",
                status="pending",
            )
        )
        session.add(
            ActivityLog(
                event_type="no_change",
                api_name="stripe",
                repo_id=repo_id,
                message=ACTIVITY_MARKER,
            )
        )
        session.commit()
    finally:
        session.close()

    yield {"a": key_a, "b": key_b, "admin": key_admin}

    # Cleanup so the dev database stays tidy.
    session = get_session()
    try:
        session.query(ActivityLog).filter_by(message=ACTIVITY_MARKER).delete()
        session.query(Patch).filter_by(file_path=PATCH_MARKER).delete()
        if repo_id is not None:
            session.query(Repo).filter_by(id=repo_id).delete()
        if snapshot_created and snapshot_id is not None:
            from database import ChangelogSnapshot

            session.query(ChangelogSnapshot).filter_by(id=snapshot_id).delete()
        session.query(User).filter(
            User.email.in_([EMAIL_A, EMAIL_B, EMAIL_ADMIN])
        ).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _get(path: str, key: str):
    return client.get(path, headers={"X-API-Key": key})


def test_owner_sees_own_patch(world):
    r = _get("/patches", world["a"])
    assert r.status_code == 200
    assert PATCH_MARKER in [p["file_path"] for p in r.json()]


def test_other_user_cannot_see_patch(world):
    r = _get("/patches", world["b"])
    assert r.status_code == 200
    assert PATCH_MARKER not in [p["file_path"] for p in r.json()]


def test_owner_sees_own_activity(world):
    r = _get("/activity", world["a"])
    assert r.status_code == 200
    assert ACTIVITY_MARKER in [e["message"] for e in r.json()]


def test_other_user_cannot_see_activity(world):
    r = _get("/activity", world["b"])
    assert r.status_code == 200
    assert ACTIVITY_MARKER not in [e["message"] for e in r.json()]


def test_other_user_stats_do_not_count_foreign_patches(world):
    assert _get("/stats", world["b"]).json()["total_patches"] == 0
    assert _get("/stats", world["a"]).json()["total_patches"] >= 1


def test_admin_sees_everything(world):
    patches = _get("/patches", world["admin"]).json()
    activity = _get("/activity", world["admin"]).json()
    assert PATCH_MARKER in [p["file_path"] for p in patches]
    assert ACTIVITY_MARKER in [e["message"] for e in activity]


@pytest.mark.parametrize("path", ["/patches", "/activity", "/stats"])
def test_no_key_is_rejected(path):
    assert client.get(path).status_code == 401


def test_delete_repo_removes_data_and_respects_ownership(world):
    session = get_session()
    try:
        owner = session.query(User).filter_by(email=EMAIL_A).first()
        snapshot_id, _ = _get_or_create_snapshot(session)
        repo = Repo(
            user_id=owner.id,
            github_url="https://github.com/isolation-test/repo-delete",
            owner="isolation-test",
            repo_name="repo-delete",
            api_name="stripe",
        )
        session.add(repo)
        session.commit()
        repo_id = repo.id
        session.add(
            Patch(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_path="isolation_delete.py",
                original_code="old",
                patched_code="new",
            )
        )
        session.add(
            ActivityLog(
                event_type="no_change",
                api_name="stripe",
                repo_id=repo_id,
                message="isolation-delete-activity",
            )
        )
        session.commit()
    finally:
        session.close()

    # Another user cannot delete it.
    r = client.delete(f"/repos/{repo_id}", headers={"X-API-Key": world["b"]})
    assert r.status_code == 404

    # No key is rejected.
    assert client.delete(f"/repos/{repo_id}").status_code == 401

    # The owner can, and everything attached is gone.
    r = client.delete(f"/repos/{repo_id}", headers={"X-API-Key": world["a"]})
    assert r.status_code == 200

    session = get_session()
    try:
        assert session.query(Repo).filter_by(id=repo_id).count() == 0
        assert session.query(Patch).filter_by(repo_id=repo_id).count() == 0
        assert session.query(ActivityLog).filter_by(repo_id=repo_id).count() == 0
    finally:
        session.close()


def _make_user_data(user_id: int, tag: str) -> int:
    """Give a user one repo, one patch and one activity row. Returns repo id."""
    session = get_session()
    try:
        snapshot_id, _ = _get_or_create_snapshot(session)
        repo = Repo(
            user_id=user_id,
            github_url=f"https://github.com/isolation-test/{tag}",
            owner="isolation-test",
            repo_name=tag,
            api_name="stripe",
        )
        session.add(repo)
        session.commit()
        session.add(
            Patch(
                repo_id=repo.id,
                snapshot_id=snapshot_id,
                file_path=f"{tag}.py",
                original_code="old",
                patched_code="new",
            )
        )
        session.add(
            ActivityLog(
                event_type="no_change",
                api_name="stripe",
                repo_id=repo.id,
                message=f"{tag}-activity",
            )
        )
        session.commit()
        return repo.id
    finally:
        session.close()


def _delete_me(key: str, email: str):
    return client.request(
        "DELETE", "/me", headers={"X-API-Key": key}, json={"confirm_email": email}
    )


def test_delete_account_removes_only_that_users_data():
    email_x, email_y = "isolation-x@patchpilot.dev", "isolation-y@patchpilot.dev"
    uid_x, key_x = _get_or_create_user(email_x)
    uid_y, key_y = _get_or_create_user(email_y)
    repo_x = _make_user_data(uid_x, "acct-x")
    repo_y = _make_user_data(uid_y, "acct-y")

    # Wrong email is rejected and nothing is deleted.
    assert _delete_me(key_x, "someone-else@example.com").status_code == 400
    # No key is rejected.
    r = client.request("DELETE", "/me", json={"confirm_email": email_x})
    assert r.status_code == 401

    # Correct email deletes the account.
    assert _delete_me(key_x, email_x).status_code == 200

    session = get_session()
    try:
        assert session.query(User).filter_by(email=email_x).count() == 0
        assert session.query(Repo).filter_by(id=repo_x).count() == 0
        assert session.query(Patch).filter_by(repo_id=repo_x).count() == 0
        assert session.query(ActivityLog).filter_by(repo_id=repo_x).count() == 0
        # The other user is untouched.
        assert session.query(User).filter_by(email=email_y).count() == 1
        assert session.query(Repo).filter_by(id=repo_y).count() == 1
        assert session.query(Patch).filter_by(repo_id=repo_y).count() == 1
    finally:
        session.close()

    # The deleted user's key no longer works; the other user's still does.
    assert _get("/patches", key_x).status_code == 401
    assert _get("/patches", key_y).status_code == 200

    # Cleanup for user Y.
    assert _delete_me(key_y, email_y).status_code == 200


def test_admin_cannot_delete_own_account(world):
    assert _delete_me(world["admin"], EMAIL_ADMIN).status_code == 403
