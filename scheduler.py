from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from activity import log_event
from logger import get_logger
from patcher.ollama_patcher import run_patcher
from pr_creator.github_pr import run_pr_creator
from scanner.repo_scanner import run_scanner
from scraper.anthropic_scraper import AnthropicScraper
from scraper.github_scraper import GitHubScraper
from scraper.openai_scraper import OpenAIScraper
from scraper.plaid_scraper import PlaidScraper
from scraper.sendgrid_scraper import SendGridScraper
from scraper.shopify_scraper import ShopifyScraper
from scraper.slack_scraper import SlackScraper
from scraper.stripe_scraper import StripeScraper
from scraper.twilio_scraper import TwilioScraper

logger = get_logger(__name__)

scheduler = AsyncIOScheduler()

SCRAPER_CLASSES = {
    "stripe": StripeScraper,
    "twilio": TwilioScraper,
    "openai": OpenAIScraper,
    "plaid": PlaidScraper,
    "sendgrid": SendGridScraper,
    "slack": SlackScraper,
    "github": GitHubScraper,
    "anthropic": AnthropicScraper,
    "shopify": ShopifyScraper,
}


async def detection_pass():
    logger.info("Starting detection pass")

    for api_name, scraper_class in SCRAPER_CLASSES.items():
        scraper = scraper_class()
        result = await scraper.check_changelog()
        if result is None:
            log_event(
                "no_change",
                f"Checked {api_name.title()} changelog — no changes detected",
                api_name=api_name,
            )
        else:
            log_event(
                "changelog_detected",
                f"{api_name.title()} API changelog changed — waiting 2h for stability check",
                api_name=api_name,
            )

    logger.info("Detection pass complete")


async def stability_pass():
    logger.info("Starting stability pass")

    from changelog_tagger import tag_snapshot
    from matcher import find_matching_repos, should_patch

    for api_name, scraper_class in SCRAPER_CLASSES.items():
        scraper = scraper_class()
        result = await scraper.verify_stability()

        if result is None:
            continue

        snapshot_id = result["snapshot_id"]
        changelog_content = result["content"]

        tag = tag_snapshot(snapshot_id, api_name)
        if not tag:
            logger.warning(f"[{api_name}] Could not tag snapshot {snapshot_id}")
            continue

        logger.info(
            f"[{api_name}] Tagged: type={tag.change_type} "
            f"features={tag.features} confidence={tag.tag_confidence}"
        )

        if not should_patch(tag.change_type):
            logger.info(
                f"[{api_name}] Change type '{tag.change_type}' — no patching needed"
            )
            log_event(
                "no_change",
                f"{api_name.title()} changelog update ({tag.change_type}) — no patching needed",
                api_name=api_name,
            )
            continue

        log_event(
            "changelog_stable",
            f"{api_name.title()} changelog confirmed stable — running pipeline",
            api_name=api_name,
        )

        matching_repos = find_matching_repos(snapshot_id, api_name)

        if not matching_repos:
            logger.info(f"[{api_name}] No repos matched — skipping")
            log_event(
                "no_change",
                f"{api_name.title()} change detected but no repos use the affected features",
                api_name=api_name,
            )
            continue

        log_event(
            "changelog_detected",
            f"{api_name.title()} breaking change — {len(matching_repos)} repo(s) affected",
            api_name=api_name,
        )

        for match in matching_repos:
            repo_id = match["repo_id"]
            github_url = match["github_url"]
            affected_files = match["affected_files"]

            logger.info(f"Processing {github_url} — affected files: {affected_files}")

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
                f"Scanned {github_url.split('/')[-1]} — {len(patches)} file(s) need patching",
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

    logger.info("Stability pass complete")


async def run_full_pipeline():
    await detection_pass()
    await stability_pass()


def start_scheduler():
    scheduler.add_job(
        detection_pass,
        trigger=IntervalTrigger(hours=4),
        id="detection_pass",
        replace_existing=True,
    )
    scheduler.add_job(
        stability_pass,
        trigger=IntervalTrigger(hours=2),
        id="stability_pass",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — detection every 4h, stability check every 2h")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
