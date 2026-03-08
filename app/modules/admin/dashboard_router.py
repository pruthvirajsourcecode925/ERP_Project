from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.admin.dashboard_service import get_dashboard_summary


router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


@router.get("/summary")
def get_dashboard_summary_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Management")),
):
    _ = current_user
    return get_dashboard_summary(db)