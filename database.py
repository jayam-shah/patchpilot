from datetime import datetime

from sqlalchemy import (
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


class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    github_url = Column(String, nullable=False)
    owner = Column(String, nullable=False)
    repo_name = Column(String, nullable=False)
    api_name = Column(String, nullable=False, default="stripe")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patches = relationship("Patch", back_populates="repo")


class ChangelogSnapshot(Base):
    __tablename__ = "changelog_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    raw_content = Column(Text, nullable=False)
    scraped_at = Column(DateTime, default=datetime.utcnow)

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
