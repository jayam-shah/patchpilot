from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import init_db, get_session, Repo, Patch
from scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    print("[App] PatchPilot started.")
    yield
    stop_scheduler()
    print("[App] PatchPilot stopped.")


app = FastAPI(
    title="PatchPilot",
    description="Automatically patches your code when APIs break.",
    version="0.1.0",
    lifespan=lifespan,
)


class RepoRegisterRequest(BaseModel):
    github_url: str
    api_name: str = "stripe"


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/repos", status_code=201)
def register_repo(request: RepoRegisterRequest):
    parts = request.github_url.rstrip("/").split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
    owner = parts[-2]
    repo_name = parts[-1]

    session = get_session()
    try:
        existing = session.query(Repo).filter_by(
            owner=owner, repo_name=repo_name
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Repo {owner}/{repo_name} already registered"
            )
        repo = Repo(
            github_url=request.github_url,
            owner=owner,
            repo_name=repo_name,
            api_name=request.api_name,
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
def list_repos():
    session = get_session()
    try:
        repos = session.query(Repo).filter_by(is_active=True).all()
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
def list_patches():
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


@app.delete("/repos/{repo_id}")
def deactivate_repo(repo_id: int):
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