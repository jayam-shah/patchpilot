from database import ChangelogTag, Repo, RepoApiUsage, get_session
from logger import get_logger

logger = get_logger(__name__)


def find_matching_repos(snapshot_id: int, service: str) -> list[dict]:
    session = get_session()
    try:
        tags = (
            session.query(ChangelogTag)
            .filter_by(snapshot_id=snapshot_id, service=service)
            .all()
        )

        if not tags:
            logger.info(f"[Matcher] No tags for snapshot {snapshot_id}/{service}")
            return []

        affected_features = set()
        change_types = set()
        for tag in tags:
            affected_features.update(tag.features or [])
            change_types.add(tag.change_type)

        logger.info(
            f"[Matcher] Snapshot {snapshot_id} [{service}]: "
            f"features={list(affected_features)} types={list(change_types)}"
        )

        if not affected_features:
            usages = session.query(RepoApiUsage).filter_by(service=service).all()
        else:
            usages = (
                session.query(RepoApiUsage)
                .filter(
                    RepoApiUsage.service == service,
                    RepoApiUsage.feature.in_(list(affected_features)),
                )
                .all()
            )

        if not usages:
            logger.info(f"[Matcher] No repos use {service}/{affected_features}")
            return []

        repo_ids = list({u.repo_id for u in usages})
        repos = (
            session.query(Repo)
            .filter(
                Repo.id.in_(repo_ids),
                Repo.is_active == True,
            )
            .all()
        )

        results = []
        for repo in repos:
            repo_usages = [u for u in usages if u.repo_id == repo.id]
            matched_files = list(
                {u.file_path for u in repo_usages if u.file_path != "manual"}
            )
            results.append(
                {
                    "repo_id": repo.id,
                    "github_url": repo.github_url,
                    "api_name": repo.api_name,
                    "matched_features": list({u.feature for u in repo_usages}),
                    "affected_files": matched_files,
                }
            )
            logger.info(
                f"[Matcher] Repo {repo.github_url} matched — "
                f"features={[u.feature for u in repo_usages]} "
                f"files={matched_files}"
            )

        return results
    finally:
        session.close()


def should_patch(change_type: str) -> bool:
    return change_type in ("breaking", "deprecation")
