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

    def get_pending_snapshot(self) -> ChangelogSnapshot | None:
        session = get_session()
        try:
            return (
                session.query(ChangelogSnapshot)
                .filter_by(api_name=self.api_name, is_stable=False)
                .order_by(ChangelogSnapshot.scraped_at.desc())
                .first()
            )
        finally:
            session.close()

    def mark_stable(self, snapshot_id: int) -> None:
        session = get_session()
        try:
            snapshot = (
                session.query(ChangelogSnapshot).filter_by(id=snapshot_id).first()
            )
            if snapshot:
                snapshot.is_stable = True
                session.commit()
                logger.info(
                    f"[{self.api_name}] Snapshot id={snapshot_id} marked stable"
                )
        finally:
            session.close()

    def save_snapshot(
        self,
        version: str,
        content_hash: str,
        raw_content: str,
        is_stable: bool = False,
    ) -> ChangelogSnapshot:
        session = get_session()
        try:
            snapshot = ChangelogSnapshot(
                api_name=self.api_name,
                version=version,
                content_hash=content_hash,
                raw_content=raw_content,
                is_stable=is_stable,
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
        snapshot = self.save_snapshot(version, current_hash, content, is_stable=False)

        logger.info(
            f"[{self.api_name}] Change detected — saved snapshot id={snapshot.id} (pending stability check)"
        )

        return {
            "snapshot_id": snapshot.id,
            "api_name": self.api_name,
            "version": version,
            "content": content,
            "previous_content": last_snapshot.raw_content if last_snapshot else None,
            "is_stable": False,
        }

    async def verify_stability(self) -> dict | None:
        from datetime import datetime

        import httpx

        pending = self.get_pending_snapshot()
        if not pending:
            return None

        logger.info(
            f"[{self.api_name}] Running stability check on snapshot id={pending.id}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            response = await client.get(self.changelog_url, timeout=30)
            response.raise_for_status()
            html = response.text

        content = self.parse_changelog(html)
        current_hash = self.hash_content(content)

        if current_hash == pending.content_hash:
            self.mark_stable(pending.id)
            logger.info(
                f"[{self.api_name}] Changelog stable — proceeding with pipeline"
            )
            return {
                "snapshot_id": pending.id,
                "api_name": self.api_name,
                "version": pending.version,
                "content": pending.raw_content,
                "is_stable": True,
            }
        else:
            version = datetime.now(tz=UTC).strftime("%Y-%m-%d-%H%M%S")
            new_snapshot = self.save_snapshot(
                version, current_hash, content, is_stable=False
            )
            logger.warning(
                f"[{self.api_name}] Changelog changed again — resetting stability timer. New snapshot id={new_snapshot.id}"
            )
            return None
