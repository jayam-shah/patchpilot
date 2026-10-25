from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from auth import verify_api_key
from database import ChangelogSnapshot, Patch, Repo, User, get_session, init_db
from logger import get_logger
from scheduler import start_scheduler, stop_scheduler

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


class UserLoginRequest(BaseModel):
    email: str
    password: str


class PatchStatusUpdate(BaseModel):
    status: str


@app.get("/health")
@limiter.limit("60/minute")
def health(request: Request):
    return {"status": "ok", "version": "0.1.0"}


@app.post("/auth/register", status_code=201)
@limiter.limit("5/minute")
def register_user(request: Request, body: UserRegisterRequest):
    from users import create_user

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
    parts = body.github_url.rstrip("/").split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
    owner = parts[-2]
    repo_name = parts[-1]

    session = get_session()
    try:
        query = session.query(Repo).filter_by(owner=owner, repo_name=repo_name)
        if current_user:
            query = query.filter_by(user_id=current_user.id)
        existing = query.first()
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
        return {
            "id": repo.id,
            "github_url": repo.github_url,
            "owner": repo.owner,
            "repo_name": repo.repo_name,
            "api_name": repo.api_name,
            "is_active": repo.is_active,
        }
    finally:
        session.close()


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
        return [
            {
                "id": r.id,
                "github_url": r.github_url,
                "owner": r.owner,
                "repo_name": r.repo_name,
                "api_name": r.api_name,
            }
            for r in repos
        ]
    finally:
        session.close()


@app.get("/patches")
@limiter.limit("30/minute")
def list_patches(
    request: Request,
    current_user: User = Depends(verify_api_key),  # noqa: B008
):
    session = get_session()
    try:
        patches = session.query(Patch).order_by(Patch.created_at.desc()).limit(50).all()
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
        if current_user and repo_ids:
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
            "apis_watched": ["Stripe", "Twilio", "OpenAI"],
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
    session = get_session()
    try:
        repo = session.query(Repo).filter_by(id=repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repo not found")
        repo.is_active = False
        session.commit()
        return {"message": f"Repo {repo_id} deactivated"}
    finally:
        session.close()


@app.get("/", response_class=HTMLResponse)
def landing():
    with open("templates/landing.html") as f:
        return f.read()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    with open("templates/index.html") as f:
        return f.read()
