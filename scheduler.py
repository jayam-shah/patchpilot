from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import get_session, Repo
from scraper.stripe_scraper import check_stripe_changelog
from scanner.repo_scanner import run_scanner
from patcher.ollama_patcher import run_patcher
from pr_creator.github_pr import run_pr_creator
from logger import get_logger
logger = get_logger(__name__)

scheduler = AsyncIOScheduler()

async def run_full_pipeline():
    logger.info("Starting scheduled run")

    result = await check_stripe_changelog()

    if result is None:
        logger.info("No change detected — skipping")
        return

    snapshot_id = result["snapshot_id"]
    changelog_content = result["content"]
    logger.info(f"Change detected — snapshot id={snapshot_id}")

    session = get_session()
    try:
        repos = session.query(Repo).filter_by(is_active=True, api_name="stripe").all()
        repo_list = [(r.id, r.github_url) for r in repos]
    finally:
        session.close()

    if not repo_list:
        logger.warning("No active repos registered")
        return

    logger.info(f"Found {len(repo_list)} active repo(s) to process")

    for repo_id, github_url in repo_list:
        logger.info(f"Processing {github_url}")

        patches = run_scanner(repo_id, github_url, snapshot_id)
        if not patches:
            logger.info("No affected files found — skipping")
            continue

        results = await run_patcher(patches, changelog_content)
        if not results:
            logger.warning("Patcher produced no output")
            continue

        pr_url = run_pr_creator(repo_id, results)
        if pr_url:
            logger.info(f"PR opened: {pr_url}")
        else:
            logger.error("PR creation failed")

    logger.info("Run complete")

def start_scheduler():
    scheduler.add_job(
        run_full_pipeline,
        trigger=IntervalTrigger(hours=24),
        id="stripe_pipeline",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — pipeline runs every 24 hours")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")