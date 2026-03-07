from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.services.production_report_service import (
    get_batch_production_report,
    get_job_progress_report,
    get_machine_utilization_report,
    get_operator_activity_report,
)
from app.services.production_service import ProductionBusinessRuleError


router = APIRouter(prefix="/production/report", tags=["production-report"])


def _raise_production_http_error(exc: ProductionBusinessRuleError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=detail)


class ReportUserOut(BaseModel):
    id: int
    username: str
    email: str


class ReportMachineOut(BaseModel):
    id: int
    machine_code: str
    machine_name: str
    work_center: str | None = None


class BatchProductionReportOut(BaseModel):
    batch_number: str
    total_produced_quantity: Decimal
    total_scrap_quantity: Decimal
    machines_used: list[ReportMachineOut]
    operators_involved: list[ReportUserOut]


class OperatorActivityReportOut(BaseModel):
    operator: ReportUserOut
    jobs_worked: int
    operations_completed: int
    total_quantity_produced: Decimal
    total_scrap: Decimal


class MachineUtilizationReportOut(BaseModel):
    machine: ReportMachineOut
    total_operations: int
    production_quantity: Decimal
    scrap_quantity: Decimal
    operators_used: list[ReportUserOut]


class JobProgressReportOut(BaseModel):
    job_number: str
    planned_quantity: Decimal
    produced_quantity: Decimal
    scrap_quantity: Decimal
    remaining_quantity: Decimal
    operations_completed: int
    operations_pending: int


@router.get("/batch", response_model=list[BatchProductionReportOut])
def get_batch_report_endpoint(
    batch_number: str | None = Query(None, min_length=1),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Management", "Admin", module="production")),
):
    del current_user
    try:
        return get_batch_production_report(
            db,
            batch_number=batch_number,
            start_date=start_date,
            end_date=end_date,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.get("/operator", response_model=list[OperatorActivityReportOut])
def get_operator_report_endpoint(
    operator_id: int | None = Query(None, ge=1),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Management", "Admin", module="production")),
):
    del current_user
    try:
        return get_operator_activity_report(
            db,
            operator_id=operator_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.get("/machine", response_model=list[MachineUtilizationReportOut])
def get_machine_report_endpoint(
    machine_id: int | None = Query(None, ge=1),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Management", "Admin", module="production")),
):
    del current_user
    try:
        return get_machine_utilization_report(
            db,
            machine_id=machine_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.get("/job", response_model=JobProgressReportOut)
def get_job_report_endpoint(
    production_order_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Management", "Admin", module="production")),
):
    del current_user
    try:
        return get_job_progress_report(
            db,
            production_order_id=production_order_id,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)
