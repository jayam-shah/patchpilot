from github import Github, GithubException
from config import GITHUB_TOKEN
from database import get_session, Repo, Patch, ChangelogSnapshot

STRIPE_PATTERNS = [
    "stripe.PaymentIntent.create",
    "stripe.Customer.create",
    "stripe.Charge.create",
    "stripe.Subscription.create",
    "stripe.PaymentMethod.attach",
    "stripe.Invoice.create",
    "stripe.Refund.create",
]

SCANNABLE_EXTENSIONS = [".py", ".js", ".ts", ".rb", ".go", ".java"]

def get_github_client() -> Github:
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN not set in .env file")
    return Github(GITHUB_TOKEN)

def parse_repo_url(github_url: str) -> tuple[str, str]:
    parts = github_url.rstrip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {github_url}")
    owner = parts[-2]
    repo_name = parts[-1]
    return owner, repo_name

def search_file_for_patterns(file_content: str, patterns: list[str]) -> list[str]:
    matched_patterns = []
    for pattern in patterns:
        if pattern in file_content:
            matched_patterns.append(pattern)
    return matched_patterns

def scan_repo(github_url: str) -> list[dict]:
    client = get_github_client()
    owner, repo_name = parse_repo_url(github_url)

    print(f"[Scanner] Scanning {owner}/{repo_name}")

    try:
        repo = client.get_repo(f"{owner}/{repo_name}")
    except GithubException as e:
        print(f"[Scanner] Could not access repo: {e.status} {e.data}")
        return []

    affected_files = []
    contents = repo.get_contents("")

    while contents:
        file_obj = contents.pop(0)

        if file_obj.type == "dir":
            contents.extend(repo.get_contents(file_obj.path))
            continue

        if not any(file_obj.name.endswith(ext) for ext in SCANNABLE_EXTENSIONS):
            continue

        try:
            file_content = file_obj.decoded_content.decode("utf-8")
        except Exception:
            continue

        matched = search_file_for_patterns(file_content, STRIPE_PATTERNS)

        if matched:
            print(f"[Scanner] Found patterns {matched} in {file_obj.path}")
            affected_files.append({
                "file_path": file_obj.path,
                "content": file_content,
                "matched_patterns": matched,
            })

    print(f"[Scanner] Done. {len(affected_files)} affected file(s) found.")
    return affected_files

def save_affected_files(repo_id: int, snapshot_id: int, affected_files: list[dict]) -> list[Patch]:
    session = get_session()
    patches = []
    try:
        for file_info in affected_files:
            patch = Patch(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_path=file_info["file_path"],
                original_code=file_info["content"],
                status="pending",
            )
            session.add(patch)
        session.commit()
        for patch in session.query(Patch).filter_by(repo_id=repo_id, status="pending").all():
            patches.append(patch)
        return patches
    finally:
        session.close()

def run_scanner(repo_db_id: int, github_url: str, snapshot_id: int) -> list[Patch]:
    affected_files = scan_repo(github_url)

    if not affected_files:
        print("[Scanner] No affected files. Nothing to patch.")
        return []

    patches = save_affected_files(repo_db_id, snapshot_id, affected_files)
    print(f"[Scanner] Saved {len(patches)} patch record(s) to database.")
    return patches

