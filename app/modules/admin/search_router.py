from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.admin.search_service import global_search


router = APIRouter(prefix="/search", tags=["admin-search"])


@router.get("")
def global_search_endpoint(
    q: str = Query(..., min_length=1, description="Search text"),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    _ = current_user
    return global_search(db, q)
