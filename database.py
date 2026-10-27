from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import DATABASE_URL

Base = declarative_base()

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    api_key = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))

    plan = Column(String, default="free")
    plan_override = Column(String, nullable=True)
    plan_expires_at = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, default=False)

    repos = relationship("Repo", back_populates="user")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    api_name = Column(String)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))


class RepoApiUsage(Base):
    __tablename__ = "repo_api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)
    service = Column(String, nullable=False)
    feature = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    line_number = Column(Integer, nullable=True)
    detected_by = Column(String, nullable=False, default="regex")
    sdk_version = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))

    repo = relationship("Repo", back_populates="api_usages")


class ChangelogTag(Base):
    __tablename__ = "changelog_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, ForeignKey("changelog_snapshots.id"), nullable=False)
    service = Column(String, nullable=False)
    features = Column(JSON, nullable=False, default=list)
    change_type = Column(String, nullable=False, default="other")
    tag_confidence = Column(String, nullable=False, default="low")
    created_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))

    snapshot = relationship("ChangelogSnapshot", back_populates="tags")


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=True)
    service_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))


class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    github_url = Column(String, nullable=False)
    owner = Column(String, nullable=False)
    repo_name = Column(String, nullable=False)
    api_name = Column(String, nullable=False, default="stripe")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))
    scan_status = Column(String, default="pending")
    last_scanned_sha = Column(String, nullable=True)
    last_scanned_at = Column(DateTime, nullable=True)

    api_usages = relationship("RepoApiUsage", back_populates="repo")
    user = relationship("User", back_populates="repos")
    patches = relationship("Patch", back_populates="repo")


class ChangelogSnapshot(Base):
    __tablename__ = "changelog_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    raw_content = Column(Text, nullable=False)
    scraped_at = Column(DateTime, default=lambda: datetime.now(tz=UTC))
    is_stable = Column(Boolean, default=False)

    tags = relationship("ChangelogTag", back_populates="snapshot")
    patches = relationship("Patch", back_populates="snapshot")


class Patch(Base):
    __tablename__ = "patches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)
    snapshot_id = Column(Integer, ForeignKey("changelog_snapshots.id"), nullable=False)
    file_path = Column(String, nullable=False)
    original_code = Column(Text)
    patched_code = Column(Text)
    pr_url = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    repo = relationship("Repo", back_populates="patches")
    snapshot = relationship("ChangelogSnapshot", back_populates="patches")


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()


def generate_api_key() -> str:
    import secrets

    return secrets.token_hex(32)
