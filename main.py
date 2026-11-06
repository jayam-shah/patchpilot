import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager

import stripe
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from activity import log_event
from auth import verify_api_key
from database import (
    ActivityLog,
    ChangelogSnapshot,
    Patch,
    Repo,
    RepoApiUsage,
    ServiceRequest,
    User,
    get_session,
    init_db,
)
from logger import get_logger
from scheduler import start_scheduler, stop_scheduler

INVITE_ONLY = True


def _valid_invite_codes() -> list[str]:
    """Codes come from the INVITE_CODES env var (comma-separated).

    Unset or empty means nobody can register (closed by default).
    """
    raw = os.getenv("INVITE_CODES", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def _invite_code_ok(code: str | None) -> bool:
    if not code:
        return False
    supplied = code.strip().encode()
    ok = False
    # Check every code (no early exit) with a constant-time compare.
    for valid in _valid_invite_codes():
        if hmac.compare_digest(supplied, valid.encode()):
            ok = True
    return ok


logger = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    logger.info("PatchPilot started")
    yield
    stop_scheduler()
    logger.info("PatchPilot stopped")


app = FastAPI(
    title="PatchPilot",
    description="Automatically patches your code when APIs break.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class RepoRegisterRequest(BaseModel):
    github_url: str
    api_name: str = "stripe"


class UserRegisterRequest(BaseModel):
    email: str
    password: str
    invite_code: str | None = None


class UserLoginRequest(BaseModel):
    email: str
    password: str


class PatchStatusUpdate(BaseModel):
    status: str


class AdminPlanUpdate(BaseModel):
    email: str
    plan_override: str | None = None
    plan_expires_at: str | None = None
    is_active: bool | None = None


@app.get("/health")
@limiter.limit("60/minute")
def health(request: Request):
    return {"status": "ok", "version": "0.1.0"}


@app.post("/auth/register", status_code=201)
@limiter.limit("5/minute")
def register_user(request: Request, body: UserRegisterRequest):
    from users import create_user

    if INVITE_ONLY and not _invite_code_ok(body.invite_code):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing invite code. PatchPilot is invite-only during the beta.",
        )

    try:
        user = create_user(body.email, body.password)
        return {
            "message": "Account created successfully",
            "email": user.email,
            "api_key": user.api_key,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/auth/login")
@limiter.limit("10/minute")
def login_user(request: Request, body: UserLoginRequest):
    from users import get_user_by_email

    user = get_user_by_email(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "message": "Login successful",
        "email": user.email,
        "api_key": user.api_key,
    }


@app.post("/repos", status_code=201)
@limiter.limit("10/minute")
def register_repo(
    request: Request,
    body: RepoRegisterRequest,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    from plans import check_api_limit, check_repo_limit

    parts = body.github_url.rstrip("/").split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
    owner = parts[-2]
    repo_name = parts[-1]

    session = get_session()
    try:
        query = session.query(Repo).filter_by(is_active=True)
        if current_user:
            query = query.filter_by(user_id=current_user.id)

        current_count = query.count()

        allowed, msg = check_repo_limit(current_user, current_count)
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

        allowed, msg = check_api_limit(current_user, body.api_name)
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

        if current_user:
            existing = (
                session.query(Repo)
                .filter_by(owner=owner, repo_name=repo_name, user_id=current_user.id)
                .first()
            )
        else:
            existing = (
                session.query(Repo).filter_by(owner=owner, repo_name=repo_name).first()
            )

        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Repo {owner}/{repo_name} already registered",
            )

        repo = Repo(
            github_url=body.github_url,
            owner=owner,
            repo_name=repo_name,
            api_name=body.api_name,
            user_id=current_user.id if current_user else None,
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)

        repo_id = repo.id
        github_url = body.github_url

    finally:
        session.close()

    import asyncio

    from scanner.usage_scanner import scan_repo_usage

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_in_executor(None, scan_repo_usage, repo_id, github_url)
        else:
            scan_repo_usage(repo_id, github_url)
    except Exception:  # noqa: BLE001
        logger.warning(f"Usage scan failed for {github_url} — will retry later")

    return {
        "id": repo_id,
        "github_url": github_url,
        "owner": owner,
        "repo_name": repo_name,
        "api_name": body.api_name,
        "is_active": True,
    }


@app.get("/repos")
@limiter.limit("30/minute")
def list_repos(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    session = get_session()
    try:
        query = session.query(Repo).filter_by(is_active=True)
        if current_user:
            query = query.filter_by(user_id=current_user.id)
        repos = query.all()

        result = []
        for r in repos:
            patches = session.query(Patch).filter_by(repo_id=r.id).all()
            last_pr = next(
                (p.pr_url for p in reversed(patches) if p.pr_url),
                None,
            )
            result.append(
                {
                    "id": r.id,
                    "github_url": r.github_url,
                    "owner": r.owner,
                    "repo_name": r.repo_name,
                    "api_name": r.api_name,
                    "patch_count": len(patches),
                    "last_pr_url": last_pr,
                }
            )
        return result
    finally:
        session.close()


@app.get("/patches")
@limiter.limit("30/minute")
def list_patches(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    # Must be logged in. No anonymous access to patch data.
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = get_session()
    try:
        query = session.query(Patch)

        # Regular users only see patches for repos THEY own.
        # Admins see everything.
        if not current_user.is_admin:
            owned_repo_ids = [
                r.id for r in session.query(Repo.id).filter_by(user_id=current_user.id)
            ]
            query = query.filter(Patch.repo_id.in_(owned_repo_ids))

        # Newest first, capped at 50.
        patches = query.order_by(Patch.created_at.desc()).limit(50).all()
        return [
            {
                "id": p.id,
                "repo_id": p.repo_id,
                "file_path": p.file_path,
                "status": p.status,
                "pr_url": p.pr_url,
                "created_at": str(p.created_at),
            }
            for p in patches
        ]
    finally:
        session.close()


@app.patch("/patches/{patch_id}")
@limiter.limit("30/minute")
def update_patch_status(
    patch_id: int,
    request: Request,
    body: PatchStatusUpdate,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    if body.status not in ("merged", "dismissed"):
        raise HTTPException(
            status_code=400, detail="Status must be merged or dismissed"
        )
    session = get_session()
    try:
        patch = session.query(Patch).filter_by(id=patch_id).first()
        if not patch:
            raise HTTPException(status_code=404, detail="Patch not found")

        if current_user:
            repo = (
                session.query(Repo)
                .filter_by(id=patch.repo_id, user_id=current_user.id)
                .first()
            )
            if not repo:
                raise HTTPException(status_code=403, detail="Not your patch")

        patch.status = body.status
        session.commit()
        return {"message": f"Patch {patch_id} marked as {body.status}"}
    finally:
        session.close()


@app.get("/stats")
@limiter.limit("30/minute")
def get_stats(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    session = get_session()
    try:
        query = session.query(Repo).filter_by(is_active=True)
        if current_user:
            query = query.filter_by(user_id=current_user.id)
        total_repos = query.count()

        repo_ids = [r.id for r in query.all()]
        patch_query = session.query(Patch)
        patch_query = patch_query.filter(Patch.repo_id.in_(repo_ids))

        total_patches = patch_query.count()
        total_prs = patch_query.filter_by(status="pr_opened").count()

        last_snapshot = (
            session.query(ChangelogSnapshot)
            .order_by(ChangelogSnapshot.scraped_at.desc())
            .first()
        )
        last_checked = str(last_snapshot.scraped_at) if last_snapshot else "Never"

        return {
            "total_repos": total_repos,
            "total_patches": total_patches,
            "total_prs": total_prs,
            "last_checked": last_checked,
            "apis_watched": [
                "Stripe",
                "Twilio",
                "OpenAI",
                "Plaid",
                "SendGrid",
                "Slack",
                "GitHub",
                "Anthropic",
                "Shopify",
            ],
        }
    finally:
        session.close()


@app.get("/activity")
@limiter.limit("30/minute")
def get_activity(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    # Must be logged in.
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = get_session()
    try:
        query = session.query(ActivityLog)

        # Regular users only see events tied to repos THEY own.
        # Events with no repo_id (global detection events, billing events)
        # match nothing here, so they stay hidden. Admins see everything.
        if not current_user.is_admin:
            owned_repo_ids = [
                r.id for r in session.query(Repo.id).filter_by(user_id=current_user.id)
            ]
            query = query.filter(ActivityLog.repo_id.in_(owned_repo_ids))

        events = query.order_by(ActivityLog.created_at.desc()).limit(30).all()
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "api_name": e.api_name,
                "message": e.message,
                "created_at": str(e.created_at),
            }
            for e in events
        ]
    finally:
        session.close()


RESET_TOKEN_MINUTES = 60
RESET_COOLDOWN_SECONDS = 60


def _utcnow_naive():
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(tzinfo=None)


def _hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _send_reset_email(to_email: str, reset_url: str) -> None:
    # Imported at call time so tests can swap the sender.
    from notifications import send_password_reset_email

    send_password_reset_email(to_email, reset_url)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@app.post("/auth/forgot")
@limiter.limit("3/minute")
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
):
    import secrets
    from datetime import timedelta

    from sqlalchemy import func

    from database import PasswordResetToken

    # Same answer whether or not the account exists.
    reply = {"message": "If that email has an account, we've sent a reset link."}
    email = body.email.strip().lower()

    session = get_session()
    try:
        user = (
            session.query(User)
            .filter(func.lower(User.email) == email, User.is_active.is_(True))
            .first()
        )
        if not user:
            return reply

        now = _utcnow_naive()
        latest = (
            session.query(PasswordResetToken)
            .filter_by(user_id=user.id)
            .order_by(PasswordResetToken.created_at.desc())
            .first()
        )
        if latest and latest.created_at > now - timedelta(
            seconds=RESET_COOLDOWN_SECONDS
        ):
            return reply  # asked again too soon: don't send another email

        # One live token per user.
        session.query(PasswordResetToken).filter_by(user_id=user.id).delete()
        raw = secrets.token_urlsafe(32)
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_reset_token(raw),
                expires_at=now + timedelta(minutes=RESET_TOKEN_MINUTES),
                created_at=now,
            )
        )
        session.commit()

        base = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
        background_tasks.add_task(
            _send_reset_email, user.email, f"{base}/reset-password?token={raw}"
        )
        return reply
    finally:
        session.close()


@app.post("/auth/reset")
@limiter.limit("10/minute")
def reset_password(request: Request, body: ResetPasswordRequest):
    from database import PasswordResetToken, generate_api_key
    from users import hash_password

    if len(body.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters."
        )

    invalid = "This reset link is invalid or has expired."
    session = get_session()
    try:
        token = (
            session.query(PasswordResetToken)
            .filter_by(token_hash=_hash_reset_token(body.token.strip()))
            .first()
        )
        now = _utcnow_naive()
        if not token or token.used_at is not None or token.expires_at < now:
            raise HTTPException(status_code=400, detail=invalid)

        user = session.query(User).filter_by(id=token.user_id).first()
        if not user:
            raise HTTPException(status_code=400, detail=invalid)

        user.hashed_password = hash_password(body.password)
        user.api_key = generate_api_key()  # signs out every existing session
        token.used_at = now
        session.commit()
        return {"message": "Password updated. You can now sign in."}
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
def reset_password_page():
    with open("templates/reset.html") as f:
        return f.read()


def _purge_repo_rows(session, repo_id: int) -> None:
    """Delete every row attached to a repo (patches, activity, scans, ...).

    Service requests are demand signals, not repo content: keep the row but
    unlink it from the repo.
    """
    from database import Base

    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.target_fullname != "repos.id":
                continue
            if table.name == "service_requests":
                session.execute(
                    table.update().where(fk.parent == repo_id).values(repo_id=None)
                )
            else:
                session.execute(table.delete().where(fk.parent == repo_id))


class DeleteAccountRequest(BaseModel):
    confirm_email: str


@app.delete("/me")
@limiter.limit("5/minute")
def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Admin accounts cannot be deleted here"
        )
    if body.confirm_email.strip().lower() != current_user.email.lower():
        raise HTTPException(status_code=400, detail="Email does not match your account")

    from database import ServiceRequest

    session = get_session()
    try:
        user = session.query(User).filter_by(id=current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Account not found")

        # 1. Stripe first. If this fails we stop, so nobody is left being
        #    billed for an account that no longer exists. A customer that is
        #    already gone counts as success, so a retry works.
        if user.stripe_customer_id:
            if not stripe.api_key:
                raise HTTPException(
                    status_code=503,
                    detail="Billing is unavailable right now. Please try again later.",
                )
            try:
                stripe.Customer.delete(user.stripe_customer_id)
            except stripe.StripeError as e:
                if getattr(e, "code", None) != "resource_missing":
                    raise HTTPException(
                        status_code=502,
                        detail="Could not cancel your subscription. Please try again.",
                    ) from e

        # 2. Repos and everything attached to them.
        repo_ids = [r.id for r in session.query(Repo.id).filter_by(user_id=user.id)]
        for repo_id in repo_ids:
            _purge_repo_rows(session, repo_id)
        session.query(Repo).filter(Repo.user_id == user.id).delete(
            synchronize_session=False
        )

        # 3. Service requests stay as an anonymous demand signal.
        session.execute(
            ServiceRequest.__table__.update()
            .where(ServiceRequest.user_id == user.id)
            .values(user_id=None)
        )

        # 4. The account itself.
        session.delete(user)
        session.commit()
        return {"message": "Account deleted"}
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/me")
@limiter.limit("30/minute")
def get_me(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    from plans import get_effective_plan, get_plan_limits

    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    plan = get_effective_plan(current_user)
    limits = get_plan_limits(current_user)

    return {
        "email": current_user.email,
        "plan": plan,
        "plan_override": current_user.plan_override,
        "plan_expires_at": (
            str(current_user.plan_expires_at) if current_user.plan_expires_at else None
        ),
        "limits": limits,
    }


@app.post("/admin/plan", include_in_schema=False)
@limiter.limit("30/minute")
def admin_update_plan(
    request: Request,
    body: AdminPlanUpdate,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    session = get_session()
    try:
        user = session.query(User).filter_by(email=body.email).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {body.email} not found")

        if body.plan_override is not None:
            user.plan_override = (
                body.plan_override if body.plan_override != "remove" else None
            )

        if body.plan_expires_at is not None:
            from datetime import UTC, datetime

            if body.plan_expires_at == "never":
                user.plan_expires_at = None
            else:
                user.plan_expires_at = datetime.fromisoformat(
                    body.plan_expires_at
                ).replace(tzinfo=UTC)

        if body.is_active is not None:
            user.is_active = body.is_active

        session.commit()
        session.refresh(user)

        from plans import get_effective_plan

        logger.info(
            f"Admin updated {body.email}: plan={get_effective_plan(user)}, active={user.is_active}"
        )

        return {
            "email": user.email,
            "plan": user.plan,
            "plan_override": user.plan_override,
            "plan_expires_at": (
                str(user.plan_expires_at) if user.plan_expires_at else None
            ),
            "is_active": user.is_active,
            "effective_plan": get_effective_plan(user),
        }
    finally:
        session.close()


@app.get("/admin/users", include_in_schema=False)
@limiter.limit("30/minute")
def admin_list_users(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    session = get_session()
    try:
        users = session.query(User).all()
        from plans import get_effective_plan

        return [
            {
                "id": u.id,
                "email": u.email,
                "plan": u.plan,
                "effective_plan": get_effective_plan(u),
                "plan_override": u.plan_override,
                "plan_expires_at": (
                    str(u.plan_expires_at) if u.plan_expires_at else None
                ),
                "is_active": u.is_active,
                "created_at": str(u.created_at),
            }
            for u in users
        ]
    finally:
        session.close()


@app.get("/admin/metrics", include_in_schema=False)
@limiter.limit("30/minute")
def get_metrics(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    session = get_session()
    try:
        from database import ServiceRequest
        from plans import get_effective_plan

        total_users = session.query(User).count()
        active_users = session.query(User).filter_by(is_active=True).count()

        plan_counts = {}
        for user in session.query(User).all():
            plan = get_effective_plan(user)
            plan_counts[plan] = plan_counts.get(plan, 0) + 1

        total_repos = session.query(Repo).filter_by(is_active=True).count()
        total_snapshots = session.query(ChangelogSnapshot).count()
        stable_snapshots = (
            session.query(ChangelogSnapshot).filter_by(is_stable=True).count()
        )

        total_patches = session.query(Patch).count()
        pr_opened = session.query(Patch).filter_by(status="pr_opened").count()
        pr_merged = session.query(Patch).filter_by(status="merged").count()
        pr_dismissed = session.query(Patch).filter_by(status="dismissed").count()

        merge_rate = round(pr_merged / pr_opened * 100, 1) if pr_opened > 0 else 0

        from database import ActivityLog

        total_events = session.query(ActivityLog).count()
        pr_events = session.query(ActivityLog).filter_by(event_type="pr_opened").count()
        breaking_events = (
            session.query(ActivityLog)
            .filter_by(event_type="changelog_detected")
            .count()
        )

        service_requests = session.query(ServiceRequest).all()
        requested_services = {}
        for sr in service_requests:
            requested_services[sr.service_name] = (
                requested_services.get(sr.service_name, 0) + 1
            )
        top_requested = sorted(
            requested_services.items(), key=lambda x: x[1], reverse=True
        )[:5]

        from database import RepoApiUsage

        usage_rows = session.query(RepoApiUsage).all()
        service_usage_counts = {}
        for u in usage_rows:
            service_usage_counts[u.service] = service_usage_counts.get(u.service, 0) + 1
        top_services = sorted(
            service_usage_counts.items(), key=lambda x: x[1], reverse=True
        )

        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "by_plan": plan_counts,
            },
            "repos": {
                "total_active": total_repos,
            },
            "changelogs": {
                "total_snapshots": total_snapshots,
                "stable_snapshots": stable_snapshots,
                "match_rate_pct": (
                    round(stable_snapshots / total_snapshots * 100, 1)
                    if total_snapshots > 0
                    else 0
                ),
            },
            "patches": {
                "total": total_patches,
                "pr_opened": pr_opened,
                "pr_merged": pr_merged,
                "pr_dismissed": pr_dismissed,
                "merge_rate_pct": merge_rate,
            },
            "activity": {
                "total_events": total_events,
                "prs_opened": pr_events,
                "breaking_changes_detected": breaking_events,
            },
            "top_requested_services": top_requested,
            "top_used_services": top_services,
        }
    finally:
        session.close()


@app.delete("/repos/{repo_id}")
@limiter.limit("10/minute")
def deactivate_repo(
    repo_id: int,
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    # Must be logged in.
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = get_session()
    try:
        repo = (
            session.query(Repo).filter_by(id=repo_id, user_id=current_user.id).first()
        )
        if not repo:
            raise HTTPException(status_code=404, detail="Repo not found")

        # Real delete: every row attached to this repo, then the repo itself.
        _purge_repo_rows(session, repo_id)
        session.delete(repo)
        session.commit()
        return {"message": f"Repo {repo_id} deleted"}
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def terms():
    with open("templates/terms.html") as f:
        return f.read()


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
def privacy():
    with open("templates/privacy.html") as f:
        return f.read()


@app.get("/repos/{repo_id}/usage")
@limiter.limit("30/minute")
def get_repo_usage(
    repo_id: int,
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    session = get_session()
    try:
        repo = session.query(Repo).filter_by(id=repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repo not found")
        if current_user and repo.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your repo")

        usages = session.query(RepoApiUsage).filter_by(repo_id=repo_id).all()
        return {
            "repo_id": repo_id,
            "scan_status": repo.scan_status,
            "last_scanned_at": (
                str(repo.last_scanned_at) if repo.last_scanned_at else None
            ),
            "usages": [
                {
                    "id": u.id,
                    "service": u.service,
                    "feature": u.feature,
                    "file_path": u.file_path,
                    "line_number": u.line_number,
                    "detected_by": u.detected_by,
                    "sdk_version": u.sdk_version,
                }
                for u in usages
            ],
        }
    finally:
        session.close()


class UsageEditRequest(BaseModel):
    action: str
    service: str
    feature: str
    usage_id: int | None = None


@app.post("/repos/{repo_id}/usage")
@limiter.limit("20/minute")
def edit_repo_usage(
    repo_id: int,
    request: Request,
    body: UsageEditRequest,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    session = get_session()
    try:
        repo = session.query(Repo).filter_by(id=repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repo not found")
        if current_user and repo.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your repo")

        if body.action == "add":
            existing = (
                session.query(RepoApiUsage)
                .filter_by(repo_id=repo_id, service=body.service, feature=body.feature)
                .first()
            )
            if existing:
                raise HTTPException(status_code=409, detail="Already exists")
            usage = RepoApiUsage(
                repo_id=repo_id,
                service=body.service,
                feature=body.feature,
                file_path="manual",
                detected_by="manual",
            )
            session.add(usage)
            session.commit()
            return {"message": f"Added {body.service}/{body.feature}"}

        elif body.action == "remove":
            if not body.usage_id:
                raise HTTPException(
                    status_code=400, detail="usage_id required for remove"
                )
            usage = (
                session.query(RepoApiUsage)
                .filter_by(id=body.usage_id, repo_id=repo_id)
                .first()
            )
            if not usage:
                raise HTTPException(status_code=404, detail="Usage not found")
            session.delete(usage)
            session.commit()
            return {"message": "Removed"}

        elif body.action == "rescan":
            from scanner.usage_scanner import scan_repo_usage

            result = scan_repo_usage(repo_id, repo.github_url)
            return {
                "message": "Rescan complete",
                "findings_count": result.get("findings_count", 0),
            }

        else:
            raise HTTPException(
                status_code=400, detail="action must be add, remove, or rescan"
            )
    finally:
        session.close()


class ServiceRequestBody(BaseModel):
    service_name: str
    repo_id: int | None = None


@app.post("/service-requests", status_code=201)
@limiter.limit("5/minute")
def request_service(
    request: Request,
    body: ServiceRequestBody,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    session = get_session()
    try:
        sr = ServiceRequest(
            user_id=current_user.id if current_user else None,
            repo_id=body.repo_id,
            service_name=body.service_name,
        )
        session.add(sr)
        session.commit()
        logger.info(
            f"Service request: {body.service_name} from user {current_user.id if current_user else 'anon'}"
        )
        return {"message": f"Thanks — we'll look into adding {body.service_name}"}
    finally:
        session.close()


@app.post("/webhooks/github", include_in_schema=False)
async def github_webhook(request: Request):
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    body = await request.body()

    if webhook_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = (
            "sha256="
            + hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        )
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body)
    event_type = request.headers.get("X-GitHub-Event", "")

    if event_type != "push":
        return {"message": "ignored"}

    repo_url = payload.get("repository", {}).get("html_url", "")
    if not repo_url:
        return {"message": "no repo url"}

    changed_files = []
    for commit in payload.get("commits", []):
        changed_files.extend(commit.get("added", []))
        changed_files.extend(commit.get("modified", []))

    session = get_session()
    try:
        repo = (
            session.query(Repo)
            .filter(
                Repo.github_url.ilike(f"%{repo_url.split('github.com/')[-1]}%"),
                Repo.is_active == True,
            )
            .first()
        )
        if not repo:
            return {"message": "repo not monitored"}
        repo_id = repo.id
        github_url = repo.github_url
    finally:
        session.close()

    import asyncio

    from scanner.usage_scanner import scan_repo_usage

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, scan_repo_usage, repo_id, github_url)

    dependency_files = {
        "requirements.txt",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "Pipfile",
    }
    has_dep_change = any(f.split("/")[-1] in dependency_files for f in changed_files)

    if has_dep_change:
        log_event(
            "no_change",
            f"Dependency file changed in {github_url.split('/')[-1]} — rescanning APIs",
            repo_id=repo_id,
        )

    logger.info(f"[Webhook] Push to {repo_url} — {len(changed_files)} files changed")
    return {"message": "rescan triggered"}


@app.get("/pricing", response_class=HTMLResponse, include_in_schema=False)
def pricing():
    with open("templates/pricing.html") as f:
        return f.read()


@app.post("/payments/create-checkout")
@limiter.limit("5/minute")
def create_checkout(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    from plans import get_effective_plan

    if get_effective_plan(current_user) == "pro":
        raise HTTPException(status_code=400, detail="You are already on the Pro plan")

    from payments import create_checkout_session

    url = create_checkout_session(current_user.email, current_user.id)
    return {"checkout_url": url}


@app.post("/webhooks/stripe", include_in_schema=False)
@app.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Invalid Stripe webhook signature: {e}")
        raise HTTPException(status_code=400, detail="invalid_signature")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail="webhook_error")

    event_type = event["type"]
    data = event["data"]["object"].to_dict()
    logger.info(f"Stripe webhook received: {event_type}")

    session = get_session()
    try:
        if event_type == "checkout.session.completed":
            raw_user_id = (data.get("metadata") or {}).get("user_id")
            user_id = (
                int(raw_user_id) if raw_user_id and str(raw_user_id).isdigit() else 0
            )
            if user_id:
                user = session.query(User).filter_by(id=user_id).first()
                if user:
                    user.plan = "pro"
                    user.plan_override = None
                    stripe_customer_id = data.get("customer")
                    if stripe_customer_id:
                        user.stripe_customer_id = stripe_customer_id
                    session.commit()
                    logger.info(f"User {user_id} upgraded to Pro")
                    log_event(
                        "no_change",
                        f"User {user.email} upgraded to Pro via Stripe",
                        api_name=None,
                    )

        elif event_type == "customer.subscription.deleted":
            stripe_customer_id = data.get("customer")
            if stripe_customer_id:
                user = (
                    session.query(User)
                    .filter_by(stripe_customer_id=stripe_customer_id)
                    .first()
                )
                if user:
                    user.plan = "free"
                    session.commit()
                    logger.info(f"User {user.email} downgraded to free")
    finally:
        session.close()

    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing():
    with open("templates/landing.html") as f:
        return f.read()


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    with open("templates/index.html") as f:
        return f.read()
