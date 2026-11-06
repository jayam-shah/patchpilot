"""GitHub App authentication helpers."""

import base64
import time

import httpx
import jwt

from config import GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_B64


def _private_key() -> str:
    if not GITHUB_APP_PRIVATE_KEY_B64:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_B64 is not set")
    return base64.b64decode(GITHUB_APP_PRIVATE_KEY_B64).decode()


def app_jwt() -> str:
    """Short-lived (9 min) token that authenticates as the app itself."""
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": str(GITHUB_APP_ID)}
    return jwt.encode(payload, _private_key(), algorithm="RS256")


if __name__ == "__main__":
    # Self-check: ask GitHub who we are.
    r = httpx.get(
        "https://api.github.com/app",
        headers={
            "Authorization": f"Bearer {app_jwt()}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    print(r.status_code, r.json().get("name") if r.is_success else r.text)
