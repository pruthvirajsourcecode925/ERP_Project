from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.admin.alerts_service import get_system_alerts
from app.modules.admin.models_alert_settings import AlertSettings


router = APIRouter(prefix="/dashboard", tags=["admin-alerts"])


class AlertSettingsUpdate(BaseModel):
    alerts_enabled: bool


class AlertSettingsResponse(BaseModel):
    alerts_enabled: bool
    created_at: datetime
    updated_at: datetime


@router.get("/alerts")
def get_dashboard_alerts(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    _ = current_user
    return get_system_alerts(db)


@router.patch("/alerts/settings", response_model=AlertSettingsResponse)
def update_alert_settings(
    payload: AlertSettingsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    settings = db.scalar(select(AlertSettings).where(AlertSettings.id == 1))
    if settings is None:
        settings = AlertSettings(
            id=1,
            alerts_enabled=payload.alerts_enabled,
            created_by=current_user.id,
        )
        db.add(settings)
    else:
        settings.alerts_enabled = payload.alerts_enabled

    db.commit()
    db.refresh(settings)
    return settings