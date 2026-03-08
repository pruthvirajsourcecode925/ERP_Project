from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.admin.audit_service import get_audit_logs


router = APIRouter(prefix="/admin", tags=["admin-audit"])


@router.get("/audit-logs")
def list_audit_logs(
    user_id: int | None = Query(default=None),
    module: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    _ = current_user
    return get_audit_logs(
        db=db,
        user_id=user_id,
        module=module,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
