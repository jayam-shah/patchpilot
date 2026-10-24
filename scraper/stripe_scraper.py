import httpx
import hashlib
from logger import get_logger
logger = get_logger(__name__)
from bs4 import BeautifulSoup
from datetime import datetime
from database import get_session, ChangelogSnapshot

STRIPE_CHANGELOG_URL = "https://docs.stripe.com/upgrades"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

async def fetch_page(url: str) -> str:
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        response = await client.get(url, timeout=30)
        response.raise_for_status()
        return response.text

def parse_changelog(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    
    main = soup.find("main") or soup.find("body")
    return main.get_text(separator="\n", strip=True) if main else soup.get_text()

def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def get_last_snapshot(api_name: str) -> ChangelogSnapshot | None:
    session = get_session()
    try:
        return (
            session.query(ChangelogSnapshot)
            .filter_by(api_name=api_name)
            .order_by(ChangelogSnapshot.scraped_at.desc())
            .first()
        )
    finally:
        session.close()

def save_snapshot(api_name: str, version: str, content_hash: str, raw_content: str) -> ChangelogSnapshot:
    session = get_session()
    try:
        snapshot = ChangelogSnapshot(
            api_name=api_name,
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

async def check_stripe_changelog() -> dict | None:
    logger.info(f"Checking Stripe changelog at {datetime.utcnow()}")

    html = await fetch_page(STRIPE_CHANGELOG_URL)
    content = parse_changelog(html)
    current_hash = hash_content(content)

    last_snapshot = get_last_snapshot("stripe")

    if last_snapshot and last_snapshot.content_hash == current_hash:
        logger.info("No changes detected")
        return None

    version = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
    snapshot = save_snapshot("stripe", version, current_hash, content)

    logger.info(f"Change detected — saved snapshot id={snapshot.id}")

    return {
        "snapshot_id": snapshot.id,
        "version": version,
        "content": content,
        "previous_content": last_snapshot.raw_content if last_snapshot else None,
    }