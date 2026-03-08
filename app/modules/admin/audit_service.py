from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, or_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def _module_from_log(log: AuditLog) -> str | None:
    if isinstance(log.new_value, dict):
        module_from_payload = log.new_value.get("reference_module")
        if module_from_payload:
            return str(module_from_payload)
    return log.table_name


def get_audit_logs(
    db: Session,
    user_id: int | None = None,
    module: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
) -> dict[str, list[dict[str, object]]]:
    safe_limit = max(1, min(limit, 500))

    stmt = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.timestamp.desc())
    )

    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)

    if module and module.strip():
        pattern = f"%{module.strip()}%"
        stmt = stmt.where(
            or_(
                AuditLog.table_name.ilike(pattern),
                AuditLog.action.ilike(pattern),
                AuditLog.new_value.cast(String).ilike(pattern),
            )
        )

    if start_date is not None:
        stmt = stmt.where(AuditLog.timestamp >= start_date)

    if end_date is not None:
        stmt = stmt.where(AuditLog.timestamp <= end_date)

    rows = db.execute(stmt.limit(safe_limit)).all()

    return {
        "logs": [
            {
                "user": username,
                "action": log.action,
                "module": _module_from_log(log),
                "timestamp": log.timestamp,
            }
            for log, username in rows
        ]
    }
