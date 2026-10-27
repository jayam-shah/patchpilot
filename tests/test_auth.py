import os

os.environ.setdefault("API_KEY", "test-key-for-ci")

from fastapi.testclient import TestClient

from database import User, get_session, init_db
from main import app

client = TestClient(app)


def setup_test_user():
    init_db()
    session = get_session()
    try:
        existing = session.query(User).filter_by(email="test-ci@patchpilot.dev").first()
        if existing:
            return existing.api_key
        from users import create_user

        user = create_user("test-ci@patchpilot.dev", "testpass123")
        return user.api_key
    finally:
        session.close()


TEST_API_KEY = setup_test_user()


def test_health_no_auth():
    response = client.get("/health")
    assert response.status_code == 200


def test_repos_without_key():
    response = client.get("/repos")
    assert response.status_code == 401


def test_repos_wrong_key():
    response = client.get("/repos", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_repos_correct_key():
    response = client.get("/repos", headers={"X-API-Key": TEST_API_KEY})
    assert response.status_code == 200
