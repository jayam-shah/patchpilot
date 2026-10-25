from passlib.context import CryptContext

from database import User, generate_api_key, get_session
from logger import get_logger

logger = get_logger(__name__)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False,
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain[:72], hashed)


def create_user(email: str, password: str) -> User:
    session = get_session()
    try:
        existing = session.query(User).filter_by(email=email).first()
        if existing:
            raise ValueError(f"Email {email} already registered")

        user = User(
            email=email,
            hashed_password=hash_password(password),
            api_key=generate_api_key(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info(f"Created user: {email}")
        return user
    finally:
        session.close()


def get_user_by_api_key(api_key: str) -> User | None:
    session = get_session()
    try:
        return session.query(User).filter_by(api_key=api_key, is_active=True).first()
    finally:
        session.close()


def get_user_by_email(email: str, password: str) -> User | None:
    session = get_session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
    finally:
        session.close()
