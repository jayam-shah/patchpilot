from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from activity import log_event
from database import Repo, get_session
from logger import get_logger
from patcher.ollama_patcher import run_patcher
from pr_creator.github_pr import run_pr_creator
from scanner.repo_scanner import run_scanner
from scraper.openai_scraper import check_openai_changelog
from scraper.stripe_scraper import check_stripe_changelog
from scraper.twilio_scraper import check_twilio_changelog

logger = get_logger(__name__)

scheduler = AsyncIOScheduler()

SCRAPERS = {
    "stripe": check_stripe_changelog,
    "twilio": check_twilio_changelog,
    "openai": check_openai_changelog,
}


async def run_full_pipeline():
    logger.info("Starting scheduled run")

    session = get_session()
    try:
        repos = session.query(Repo).filter_by(is_active=True).all()
        repo_list = [(r.id, r.github_url, r.api_name) for r in repos]
    finally:
        session.close()

    if not repo_list:
        logger.warning("No active repos registered")
        return

    api_names = {api_name for _, _, api_name in repo_list}

    for api_name in api_names:
        scraper_fn = SCRAPERS.get(api_name)
        if not scraper_fn:
            logger.warning(f"No scraper found for {api_name}")
            continue

        result = await scraper_fn()

        if result is None:
            logger.info(f"[{api_name}] No change detected")
            log_event(
                "no_change",
                f"Checked {api_name.title()} changelog — no changes detected",
                api_name=api_name,
            )
            continue

        log_event(
            "changelog_detected",
            f"{api_name.title()} API changelog changed — scanning affected repos",
            api_name=api_name,
        )

        snapshot_id = result["snapshot_id"]
        changelog_content = result["content"]
        logger.info(f"[{api_name}] Change detected — snapshot id={snapshot_id}")

        for repo_id, github_url, repo_api_name in repo_list:
            if repo_api_name != api_name:
                continue

            logger.info(f"Processing {github_url}")
            patches = run_scanner(repo_id, github_url, snapshot_id, api_name)

            if not patches:
                log_event(
                    "scan_complete",
                    f"Scanned {github_url.split('/')[-1]} — no affected files found",
                    api_name=api_name,
                    repo_id=repo_id,
                )
                continue

            log_event(
                "scan_complete",
                f"Scanned {github_url.split('/')[-1]} — found {len(patches)} affected file(s)",
                api_name=api_name,
                repo_id=repo_id,
            )

            results = await run_patcher(patches, changelog_content)
            if not results:
                continue

            pr_url = run_pr_creator(repo_id, results)
            if pr_url:
                logger.info(f"PR opened: {pr_url}")
                log_event(
                    "pr_opened",
                    f"Pull request opened for {github_url.split('/')[-1]}",
                    api_name=api_name,
                    repo_id=repo_id,
                )

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
