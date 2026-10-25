import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from database import User
from logger import get_logger

logger = get_logger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str = Security(api_key_header)) -> User:
    from users import get_user_by_api_key

    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    admin_key = os.getenv("API_KEY")
    if admin_key and key == admin_key:
        return None

    user = get_user_by_api_key(key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return user
