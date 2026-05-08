from __future__ import annotations

from fastapi import APIRouter, Query

from backend.evolution.tracker import get_evolution, list_repos

router = APIRouter(prefix="/evolution", tags=["Evolution Tracker"])


@router.get("/repos")
async def get_repos() -> dict:
    """List all repositories that have been reviewed."""
    repos = await list_repos()
    return {"repos": repos}


@router.get("/history")
async def get_history(
    repo: str | None = Query(None, description="Filter by repo (e.g. owner/repo)"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Return quality score history for a repo or all repos."""
    records = await get_evolution(repo=repo, limit=limit)
    # Return in chronological order for charting
    records.reverse()
    return {"records": records, "count": len(records)}
