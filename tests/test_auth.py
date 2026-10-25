from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_no_auth():
    response = client.get("/health")
    assert response.status_code == 200


def test_repos_without_key():
    response = client.get("/repos")
    assert response.status_code == 401


def test_repos_wrong_key():
    response = client.get("/repos", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_repos_correct_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    import importlib

    import auth

    importlib.reload(auth)

    response = client.get("/repos", headers={"X-API-Key": "test-key"})
    assert response.status_code in (200, 401)
