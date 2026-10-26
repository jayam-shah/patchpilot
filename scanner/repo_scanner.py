from github import Github, GithubException

from config import GITHUB_TOKEN
from database import Patch, get_session
from logger import get_logger

logger = get_logger(__name__)

API_PATTERNS = {
    "stripe": [
        "stripe.PaymentIntent.create",
        "stripe.Customer.create",
        "stripe.Charge.create",
        "stripe.Subscription.create",
        "stripe.PaymentMethod.attach",
        "stripe.Invoice.create",
        "stripe.Refund.create",
    ],
    "twilio": [
        "client.messages.create",
        "twilio.rest.Client",
        "MessagingResponse",
        "client.calls.create",
        "client.verify",
    ],
    "openai": [
        "openai.ChatCompletion.create",
        "client.chat.completions.create",
        "openai.Completion.create",
        "openai.Embedding.create",
        "client.embeddings.create",
        "openai.Image.create",
    ],
    "plaid": [
        "plaid.api.plaid_api",
        "PlaidClient",
        "LinkTokenCreateRequest",
        "transactions_get",
        "accounts_get",
        "auth_get",
        "identity_get",
        "client.link_token_create",
        "client.transactions_sync",
    ],
}

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


def scan_repo(github_url: str, api_name: str = "stripe") -> list[dict]:
    client = get_github_client()
    owner, repo_name = parse_repo_url(github_url)
    patterns = API_PATTERNS.get(api_name, API_PATTERNS["stripe"])
    logger.info(f"Scanning {owner}/{repo_name} for {api_name} patterns")

    try:
        repo = client.get_repo(f"{owner}/{repo_name}")
    except GithubException as e:
        logger.error(f"Could not access repo: {e.status} — {e.data}")
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
        except (UnicodeDecodeError, AttributeError) as e:
            logger.debug(f"Skipping {file_obj.path}: {e}")
            continue

        matched = search_file_for_patterns(file_content, patterns)

        if matched:
            logger.debug(f"Found patterns {matched} in {file_obj.path}")
            affected_files.append(
                {
                    "file_path": file_obj.path,
                    "content": file_content,
                    "matched_patterns": matched,
                }
            )

    logger.info(f"Done — {len(affected_files)} affected file(s) found")
    return affected_files


def save_affected_files(
    repo_id: int, snapshot_id: int, affected_files: list[dict]
) -> list[Patch]:
    session = get_session()
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
        return list(
            session.query(Patch).filter_by(repo_id=repo_id, status="pending").all()
        )
    finally:
        session.close()


def run_scanner(
    repo_db_id: int, github_url: str, snapshot_id: int, api_name: str = "stripe"
) -> list[Patch]:
    affected_files = scan_repo(github_url, api_name)

    if not affected_files:
        logger.info("No affected files found")
        return []

    patches = save_affected_files(repo_db_id, snapshot_id, affected_files)
    logger.info(f"Saved {len(patches)} patch record(s) to database")
    return patches
