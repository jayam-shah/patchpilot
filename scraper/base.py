import hashlib
from abc import ABC, abstractmethod
from datetime import UTC

from database import ChangelogSnapshot, get_session
from logger import get_logger

logger = get_logger(__name__)


class BaseAPIScraper(ABC):

    @property
    @abstractmethod
    def api_name(self) -> str:
        pass

    @property
    @abstractmethod
    def changelog_url(self) -> str:
        pass

    @abstractmethod
    def parse_changelog(self, html: str) -> str:
        pass

    def hash_content(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_last_snapshot(self) -> ChangelogSnapshot | None:
        session = get_session()
        try:
            return (
                session.query(ChangelogSnapshot)
                .filter_by(api_name=self.api_name)
                .order_by(ChangelogSnapshot.scraped_at.desc())
                .first()
            )
        finally:
            session.close()

    def save_snapshot(
        self, version: str, content_hash: str, raw_content: str
    ) -> ChangelogSnapshot:

        session = get_session()
        try:
            snapshot = ChangelogSnapshot(
                api_name=self.api_name,
                version=version,
                content_hash=content_hash,
                raw_content=raw_content,
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot
        finally:
            session.close()

    async def check_changelog(self) -> dict | None:
        from datetime import datetime

        import httpx

        logger.info(f"[{self.api_name}] Checking changelog at {datetime.now(tz=UTC)}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            response = await client.get(self.changelog_url, timeout=30)
            response.raise_for_status()
            html = response.text

        content = self.parse_changelog(html)
        current_hash = self.hash_content(content)
        last_snapshot = self.get_last_snapshot()

        if last_snapshot and last_snapshot.content_hash == current_hash:
            logger.info(f"[{self.api_name}] No changes detected")
            return None

        version = datetime.now(tz=UTC).strftime("%Y-%m-%d-%H%M%S")
        snapshot = self.save_snapshot(version, current_hash, content)

        logger.info(
            f"[{self.api_name}] Change detected — saved snapshot id={snapshot.id}"
        )

        return {
            "snapshot_id": snapshot.id,
            "api_name": self.api_name,
            "version": version,
            "content": content,
            "previous_content": last_snapshot.raw_content if last_snapshot else None,
        }
