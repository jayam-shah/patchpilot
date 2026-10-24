from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import get_session, Repo
from scraper.stripe_scraper import check_stripe_changelog
from scanner.repo_scanner import run_scanner
from patcher.ollama_patcher import run_patcher
from pr_creator.github_pr import run_pr_creator

scheduler = AsyncIOScheduler()

async def run_full_pipeline():
    print("[Scheduler] Starting scheduled run...")

    result = await check_stripe_changelog()

    if result is None:
        print("[Scheduler] No change detected. Nothing to do.")
        return

    snapshot_id = result["snapshot_id"]
    changelog_content = result["content"]
    print(f"[Scheduler] Change detected. Snapshot id={snapshot_id}")

    session = get_session()
    try:
        repos = session.query(Repo).filter_by(is_active=True, api_name="stripe").all()
        repo_list = [(r.id, r.github_url) for r in repos]
    finally:
        session.close()

    if not repo_list:
        print("[Scheduler] No active repos registered. Skipping.")
        return

    print(f"[Scheduler] Found {len(repo_list)} active repo(s) to process.")

    for repo_id, github_url in repo_list:
        print(f"[Scheduler] --- Processing {github_url} ---")

        patches = run_scanner(repo_id, github_url, snapshot_id)
        if not patches:
            print(f"[Scheduler] No affected files found. Skipping.")
            continue

        results = await run_patcher(patches, changelog_content)
        if not results:
            print(f"[Scheduler] Patcher produced no output. Skipping.")
            continue

        pr_url = run_pr_creator(repo_id, results)
        if pr_url:
            print(f"[Scheduler] PR opened: {pr_url}")
        else:
            print(f"[Scheduler] PR creation failed.")

    print("[Scheduler] Run complete.")

def start_scheduler():
    scheduler.add_job(
        run_full_pipeline,
        trigger=IntervalTrigger(hours=24),
        id="stripe_pipeline",
        replace_existing=True,
    )
    scheduler.start()
    print("[Scheduler] Started. Pipeline will run every 24 hours.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Stopped.")