from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.production.models import (
    FAITriggerStatus,
    InspectionResult,
    ProductionOrder,
    ProductionOperationStatus,
    ProductionOrderStatus,
    ReworkOrderStatus,
)
from app.services.production_service import (
    ProductionBusinessRuleError,
    assign_operator_to_operation,
    close_rework_order,
    complete_operation,
    complete_production_order,
    create_machine,
    create_production_order,
    create_rework_order,
    get_production_order,
    list_machines,
    list_production_orders,
    record_inprocess_inspection,
    record_production_log,
    release_production_order,
    start_operation,
    start_production_order,
)

router = APIRouter(prefix="/production", tags=["production"])


def _raise_production_http_error(exc: ProductionBusinessRuleError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=detail)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MachineCreate(BaseModel):
    machine_code: str
    machine_name: str
    work_center: str
    is_active: bool = True


class MachineOut(BaseModel):
    id: int
    machine_code: str
    machine_name: str
    work_center: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FAITriggerOut(BaseModel):
    id: int
    production_order_id: int
    operation_id: int
    triggered_at: datetime
    status: FAITriggerStatus

    model_config = {"from_attributes": True}


class ProductionLogOut(BaseModel):
    id: int
    production_order_id: int
    operation_id: int
    produced_quantity: Decimal
    scrap_quantity: Decimal
    recorded_by: int
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ProductionOperationOut(BaseModel):
    id: int
    production_order_id: int
    operation_number: int
    operation_name: str
    machine_id: int | None
    status: ProductionOperationStatus
    started_at: datetime | None
    completed_at: datetime | None
    machine: MachineOut | None = None

    model_config = {"from_attributes": True}


class ProductionOrderCreate(BaseModel):
    production_order_number: str
    sales_order_id: int
    route_card_id: int
    planned_quantity: Decimal
    due_date: date
    start_date: date | None = None


class ProductionOrderOut(BaseModel):
    id: int
    production_order_number: str
    sales_order_id: int
    route_card_id: int
    planned_quantity: Decimal
    status: ProductionOrderStatus
    start_date: date | None
    due_date: date
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductionOrderDetailOut(ProductionOrderOut):
    operations: list[ProductionOperationOut] = Field(default_factory=list)
    logs: list[ProductionLogOut] = Field(default_factory=list)
    fai_triggers: list[FAITriggerOut] = Field(default_factory=list)


class AssignOperatorRequest(BaseModel):
    operator_user_id: int


class OperationOperatorOut(BaseModel):
    id: int
    production_operation_id: int
    operator_user_id: int
    assigned_at: datetime

    model_config = {"from_attributes": True}


class InspectionCreate(BaseModel):
    inspection_result: InspectionResult
    inspected_by: int | None = None
    remarks: str | None = None
    inspection_time: datetime | None = None


class InProcessInspectionOut(BaseModel):
    id: int
    production_operation_id: int
    inspected_by: int | None
    inspection_result: InspectionResult
    remarks: str | None
    inspection_time: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReworkCreate(BaseModel):
    production_operation_id: int
    reason: str


class ReworkOrderOut(BaseModel):
    id: int
    production_operation_id: int
    reason: str
    status: ReworkOrderStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InspectionActionOut(BaseModel):
    inspection: InProcessInspectionOut
    rework_order: ReworkOrderOut | None = None


class ProductionLogCreate(BaseModel):
    production_order_id: int
    operation_id: int
    produced_quantity: Decimal
    scrap_quantity: Decimal
    recorded_at: datetime | None = None


class OperationCompleteOut(BaseModel):
    operation: ProductionOperationOut
    fai_trigger: FAITriggerOut | None = None


@router.post("/order", response_model=ProductionOrderOut, status_code=status.HTTP_201_CREATED)
def create_production_order_endpoint(
    payload: ProductionOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        production_order = create_production_order(
            db,
            production_order_number=payload.production_order_number,
            sales_order_id=payload.sales_order_id,
            route_card_id=payload.route_card_id,
            planned_quantity=payload.planned_quantity,
            due_date=payload.due_date,
            start_date=payload.start_date,
            created_by=current_user.id,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)

    return production_order


@router.get("/order", response_model=list[ProductionOrderOut])
def list_production_orders_endpoint(
    q: str | None = Query(None, min_length=1),
    status_filter: ProductionOrderStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    _ = current_user
    stmt = select(
        ProductionOrder.id,
        ProductionOrder.production_order_number,
        ProductionOrder.sales_order_id,
        ProductionOrder.route_card_id,
        ProductionOrder.planned_quantity,
        ProductionOrder.status,
        ProductionOrder.start_date,
        ProductionOrder.due_date,
        ProductionOrder.created_at,
        ProductionOrder.updated_at,
    ).where(ProductionOrder.is_deleted.is_(False))

    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(ProductionOrder.production_order_number.ilike(pattern))
    if status_filter is not None:
        stmt = stmt.where(ProductionOrder.status == status_filter)

    stmt = stmt.order_by(ProductionOrder.id.desc()).offset(skip).limit(limit)
    return [dict(row) for row in db.execute(stmt).mappings().all()]


@router.get("/order/{id}", response_model=ProductionOrderDetailOut)
def get_production_order_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return get_production_order(db, production_order_id=id)
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.patch("/order/{id}/release", response_model=ProductionOrderOut)
def release_production_order_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return release_production_order(db, production_order_id=id, released_by=current_user.id)
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.patch("/order/{id}/start", response_model=ProductionOrderOut)
def start_production_order_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return start_production_order(db, production_order_id=id, started_by=current_user.id)
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.patch("/order/{id}/complete", response_model=ProductionOrderOut)
def complete_production_order_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return complete_production_order(db, production_order_id=id, completed_by=current_user.id)
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.post("/operation/{id}/start", response_model=ProductionOperationOut)
def start_operation_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return start_operation(db, production_operation_id=id, started_by=current_user.id)
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.post("/operation/{id}/complete", response_model=OperationCompleteOut)
def complete_operation_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        operation, fai_trigger = complete_operation(db, production_operation_id=id, completed_by=current_user.id)
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)

    return OperationCompleteOut(operation=operation, fai_trigger=fai_trigger)


@router.post("/operation/{id}/assign-operator", response_model=OperationOperatorOut, status_code=status.HTTP_201_CREATED)
def assign_operator_to_operation_endpoint(
    id: int,
    payload: AssignOperatorRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return assign_operator_to_operation(
            db,
            production_operation_id=id,
            operator_user_id=payload.operator_user_id,
            assigned_by=current_user.id,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.post("/operation/{id}/inspection", response_model=InspectionActionOut, status_code=status.HTTP_201_CREATED)
def record_inprocess_inspection_endpoint(
    id: int,
    payload: InspectionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        inspection, rework_order = record_inprocess_inspection(
            db,
            production_operation_id=id,
            inspection_result=payload.inspection_result,
            inspected_by=payload.inspected_by or current_user.id,
            remarks=payload.remarks,
            inspection_time=_parse_datetime(payload.inspection_time),
            created_by=current_user.id,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)

    return InspectionActionOut(inspection=inspection, rework_order=rework_order)


@router.post("/rework", response_model=ReworkOrderOut, status_code=status.HTTP_201_CREATED)
def create_rework_order_endpoint(
    payload: ReworkCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return create_rework_order(
            db,
            production_operation_id=payload.production_operation_id,
            reason=payload.reason,
            created_by=current_user.id,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.patch("/rework/{id}/close", response_model=ReworkOrderOut)
def close_rework_order_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return close_rework_order(
            db,
            rework_order_id=id,
            closed_by=current_user.id,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.post("/log", response_model=ProductionLogOut, status_code=status.HTTP_201_CREATED)
def record_production_log_endpoint(
    payload: ProductionLogCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return record_production_log(
            db,
            production_order_id=payload.production_order_id,
            operation_id=payload.operation_id,
            produced_quantity=payload.produced_quantity,
            scrap_quantity=payload.scrap_quantity,
            recorded_by=current_user.id,
            created_by=current_user.id,
            recorded_at=_parse_datetime(payload.recorded_at),
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)


@router.get("/machine", response_model=list[MachineOut])
def list_machines_endpoint(
    q: str | None = Query(None, min_length=1),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    return list_machines(
        db,
        q=q,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.post("/machine", response_model=MachineOut, status_code=status.HTTP_201_CREATED)
def create_machine_endpoint(
    payload: MachineCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Production", "Admin")),
):
    try:
        return create_machine(
            db,
            machine_code=payload.machine_code,
            machine_name=payload.machine_name,
            work_center=payload.work_center,
            is_active=payload.is_active,
            created_by=current_user.id,
        )
    except ProductionBusinessRuleError as exc:
        _raise_production_http_error(exc)
