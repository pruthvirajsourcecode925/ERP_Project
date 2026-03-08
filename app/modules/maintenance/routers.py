from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.maintenance.models import MaintenanceMachine, PreventiveMaintenancePlan
from app.modules.maintenance.schemas import (
    BreakdownReportCreate,
    BreakdownReportResponse,
    MachineCreate,
    MachineDowntimeCreate,
    MachineDowntimeResponse,
    MachineResponse,
    MaintenanceWorkOrderCreate,
    MaintenanceWorkOrderResponse,
    PreventiveMaintenancePlanCreate,
    PreventiveMaintenancePlanResponse,
)
from app.modules.maintenance.services import (
    MaintenanceBusinessRuleError,
    complete_work_order,
    create_machine,
    create_preventive_plan,
    create_work_order,
    get_machine_history,
    record_machine_downtime,
    report_breakdown,
)


router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class CompleteWorkOrderRequest(BaseModel):
    actual_start_at: Any | None = None
    actual_end_at: Any | None = None
    root_cause: str | None = None
    repair_action: str | None = None
    breakdown_status: str | None = None


def _raise_maintenance_http_error(exc: MaintenanceBusinessRuleError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=detail)


@router.post("/machine", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
def create_machine_endpoint(
    payload: MachineCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Admin")),
):
    try:
        return create_machine(db, payload, current_user)
    except MaintenanceBusinessRuleError as exc:
        _raise_maintenance_http_error(exc)


@router.get("/machine", response_model=list[MachineResponse])
def list_machines_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Production", "Admin", module="maintenance")),
):
    _ = current_user
    return db.scalars(
        select(MaintenanceMachine).where(MaintenanceMachine.is_deleted.is_(False)).order_by(MaintenanceMachine.id.desc())
    ).all()


@router.post("/preventive-plan", response_model=PreventiveMaintenancePlanResponse, status_code=status.HTTP_201_CREATED)
def create_preventive_plan_endpoint(
    payload: PreventiveMaintenancePlanCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Admin")),
):
    try:
        return create_preventive_plan(db, payload, current_user)
    except MaintenanceBusinessRuleError as exc:
        _raise_maintenance_http_error(exc)


@router.get("/preventive-plan", response_model=list[PreventiveMaintenancePlanResponse])
def list_preventive_plans_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Production", "Admin", module="maintenance")),
):
    _ = current_user
    return db.scalars(
        select(PreventiveMaintenancePlan)
        .where(PreventiveMaintenancePlan.is_deleted.is_(False))
        .order_by(PreventiveMaintenancePlan.id.desc())
    ).all()


@router.post("/breakdown", response_model=BreakdownReportResponse, status_code=status.HTTP_201_CREATED)
def report_breakdown_endpoint(
    payload: BreakdownReportCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Admin")),
):
    try:
        return report_breakdown(db, payload, current_user)
    except MaintenanceBusinessRuleError as exc:
        _raise_maintenance_http_error(exc)


@router.post("/work-order", response_model=MaintenanceWorkOrderResponse, status_code=status.HTTP_201_CREATED)
def create_work_order_endpoint(
    payload: MaintenanceWorkOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Admin")),
):
    try:
        return create_work_order(db, payload, current_user)
    except MaintenanceBusinessRuleError as exc:
        _raise_maintenance_http_error(exc)


@router.patch("/work-order/{id}/complete", response_model=MaintenanceWorkOrderResponse)
def complete_work_order_endpoint(
    id: int,
    payload: CompleteWorkOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Admin")),
):
    try:
        return complete_work_order(db, id, payload, current_user)
    except MaintenanceBusinessRuleError as exc:
        _raise_maintenance_http_error(exc)


@router.post("/downtime", response_model=MachineDowntimeResponse, status_code=status.HTTP_201_CREATED)
def record_machine_downtime_endpoint(
    payload: MachineDowntimeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Admin")),
):
    try:
        return record_machine_downtime(db, payload, current_user)
    except MaintenanceBusinessRuleError as exc:
        _raise_maintenance_http_error(exc)


@router.get("/history/{machine_id}")
def get_machine_history_endpoint(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Maintenance", "Production", "Admin", module="maintenance")),
):
    _ = current_user
    try:
        history = get_machine_history(db, machine_id)
    except MaintenanceBusinessRuleError as exc:
        _raise_maintenance_http_error(exc)

    return {
        "machine_id": history["machine_id"],
        "history": history["history"],
        "preventive_maintenance_records": history["preventive_maintenance_records"],
        "breakdowns": history["breakdowns"],
        "work_orders": history["work_orders"],
        "downtimes": history["downtimes"],
    }
