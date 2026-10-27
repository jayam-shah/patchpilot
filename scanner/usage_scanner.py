import ast
import re
from datetime import UTC, datetime

from github import GithubException

from config import GITHUB_TOKEN  # noqa: F401
from database import Repo, RepoApiUsage, get_session
from feature_catalog import FEATURE_CATALOG
from logger import get_logger
from scanner.repo_scanner import get_github_client, parse_repo_url

logger = get_logger(__name__)

DEPENDENCY_FILES = [
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Pipfile",
]

SDK_TO_SERVICE = {
    "openai": "openai",
    "stripe": "stripe",
    "twilio": "twilio",
    "plaid": "plaid",
    "sendgrid": "sendgrid",
    "slack-sdk": "slack",
    "slack_sdk": "slack",
    "slack-bolt": "slack",
    "PyGithub": "github",
    "pygithub": "github",
    "anthropic": "anthropic",
    "shopifyapi": "shopify",
    "ShopifyAPI": "shopify",
}


def scan_dependency_file(content: str, file_name: str) -> dict[str, str]:
    found = {}

    if file_name in ("requirements.txt", "Pipfile"):
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pkg = re.split(r"[>=<!~\[]", line)[0].strip().lower()
            for sdk, service in SDK_TO_SERVICE.items():
                if pkg == sdk.lower():
                    version_match = re.search(r"[>=<]+([0-9.]+)", line)
                    version = version_match.group(1) if version_match else None
                    found[service] = version
                    break

    elif file_name == "package.json":
        import json

        try:
            data = json.loads(content)
            deps = {}
            deps.update(data.get("dependencies", {}))
            deps.update(data.get("devDependencies", {}))
            for pkg, version in deps.items():
                for sdk, service in SDK_TO_SERVICE.items():
                    if pkg.lower() == sdk.lower():
                        found[service] = version.lstrip("^~>=")
                        break
        except (json.JSONDecodeError, KeyError):
            pass

    elif file_name in ("pyproject.toml", "setup.cfg"):
        for line in content.splitlines():
            for sdk, service in SDK_TO_SERVICE.items():
                if sdk.lower() in line.lower():
                    found[service] = None

    return found


def _node_to_str(node) -> str:
    try:
        if isinstance(node, ast.Attribute):
            value = _node_to_str(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Call):
            return _node_to_str(node.func)
        elif isinstance(node, ast.Constant):
            return str(node.value)
    except Exception:  # noqa: BLE001, S110
        pass
    return ""


def scan_python_file_ast(content: str, file_path: str) -> list[dict]:
    findings = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Call, ast.Attribute)):
            continue

        call_str = _node_to_str(node)
        if not call_str:
            continue

        for service, features in FEATURE_CATALOG.items():
            for feature, patterns in features.items():
                for pattern in patterns:
                    if pattern in call_str:
                        findings.append(
                            {
                                "service": service,
                                "feature": feature,
                                "file_path": file_path,
                                "line_number": getattr(node, "lineno", None),
                                "detected_by": "ast",
                                "matched_pattern": pattern,
                            }
                        )
                        break

    return findings


def scan_file_regex(content: str, file_path: str) -> list[dict]:
    findings = []
    lines = content.splitlines()

    for service, features in FEATURE_CATALOG.items():
        for feature, patterns in features.items():
            for pattern in patterns:
                for line_num, line in enumerate(lines, 1):
                    if pattern in line:
                        findings.append(
                            {
                                "service": service,
                                "feature": feature,
                                "file_path": file_path,
                                "line_number": line_num,
                                "detected_by": "regex",
                                "matched_pattern": pattern,
                            }
                        )
                        break

    return findings


def deduplicate_findings(findings: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for f in findings:
        key = (f["service"], f["feature"], f["file_path"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def save_usage_findings(
    repo_id: int,
    findings: list[dict],
    sdk_versions: dict[str, str],
) -> int:
    session = get_session()
    try:
        session.query(RepoApiUsage).filter_by(repo_id=repo_id).delete()
        session.commit()

        for f in findings:
            usage = RepoApiUsage(
                repo_id=repo_id,
                service=f["service"],
                feature=f["feature"],
                file_path=f["file_path"],
                line_number=f.get("line_number"),
                detected_by=f.get("detected_by", "regex"),
                sdk_version=sdk_versions.get(f["service"]),
            )
            session.add(usage)

        session.commit()
        return len(findings)
    finally:
        session.close()


def update_scan_status(repo_id: int, status: str, sha: str | None = None) -> None:
    session = get_session()
    try:
        repo = session.query(Repo).filter_by(id=repo_id).first()
        if repo:
            repo.scan_status = status
            repo.last_scanned_at = datetime.now(tz=UTC)
            if sha:
                repo.last_scanned_sha = sha
            session.commit()
    finally:
        session.close()


def scan_repo_usage(repo_id: int, github_url: str) -> dict:
    logger.info(f"[UsageScanner] Starting usage scan for {github_url}")
    update_scan_status(repo_id, "pending")

    try:
        client = get_github_client()
        owner, repo_name = parse_repo_url(github_url)
        repo = client.get_repo(f"{owner}/{repo_name}")
        latest_sha = repo.get_branch(repo.default_branch).commit.sha
    except GithubException as e:
        logger.error(f"[UsageScanner] Cannot access repo: {e.status}")
        update_scan_status(repo_id, "error")
        return {"status": "error", "findings": []}

    sdk_versions: dict[str, str] = {}
    all_findings: list[dict] = []
    contents = repo.get_contents("")
    files_scanned = 0

    while contents:
        file_obj = contents.pop(0)

        if file_obj.type == "dir":
            try:
                contents.extend(repo.get_contents(file_obj.path))
            except GithubException:
                pass
            continue

        try:
            file_content = file_obj.decoded_content.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            continue

        if file_obj.name in DEPENDENCY_FILES:
            versions = scan_dependency_file(file_content, file_obj.name)
            sdk_versions.update(versions)
            logger.debug(f"[UsageScanner] Found SDKs in {file_obj.name}: {versions}")
            continue

        if file_obj.name.endswith(".py"):
            findings = scan_python_file_ast(file_content, file_obj.path)
            if not findings:
                findings = scan_file_regex(file_content, file_obj.path)
        elif file_obj.name.endswith((".js", ".ts", ".jsx", ".tsx", ".rb", ".go")):
            findings = scan_file_regex(file_content, file_obj.path)
        else:
            continue

        all_findings.extend(findings)
        files_scanned += 1

    unique_findings = deduplicate_findings(all_findings)

    if not unique_findings and not sdk_versions:
        update_scan_status(repo_id, "no_supported_apis", latest_sha)
        logger.info(f"[UsageScanner] No supported APIs found in {github_url}")
        return {"status": "no_supported_apis", "findings": []}

    count = save_usage_findings(repo_id, unique_findings, sdk_versions)
    update_scan_status(repo_id, "scanned", latest_sha)

    services_found = list({f["service"] for f in unique_findings})
    logger.info(
        f"[UsageScanner] Done — {count} usage(s) found across "
        f"{files_scanned} files. Services: {services_found}"
    )

    return {
        "status": "scanned",
        "findings_count": count,
        "services_found": services_found,
        "sdk_versions": sdk_versions,
        "findings": unique_findings,
    }
