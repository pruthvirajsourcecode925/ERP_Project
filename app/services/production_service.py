from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.role import Role
from app.models.user import User
from app.modules.engineering.models import RouteCard, RouteCardStatus
from app.modules.production.models import (
    FAITrigger,
    FAITriggerStatus,
    InProcessInspection,
    InspectionResult,
    Machine,
    OperationOperator,
    ProductionLog,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
    ProductionOrderStatus,
    ReworkOrder,
    ReworkOrderStatus,
)
from app.modules.sales.models import SalesOrder


class ProductionBusinessRuleError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _get_user(db: Session, user_id: int) -> User:
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_deleted.is_(False),
        )
    )
    if not user:
        raise ProductionBusinessRuleError("User not found")
    return user


def _get_production_operator_user(db: Session, user_id: int) -> User:
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_deleted.is_(False),
        )
    )
    if not user:
        raise ProductionBusinessRuleError("Operator user not found")

    role = db.scalar(select(Role).where(Role.id == user.role_id))
    if not role or role.name != "Production":
        raise ProductionBusinessRuleError("Operator user must have Production role")
    return user


def _user_has_role(db: Session, user: User, role_name: str) -> bool:
    role = db.scalar(select(Role).where(Role.id == user.role_id))
    return bool(role and role.name == role_name)


def _get_sales_order(db: Session, sales_order_id: int) -> SalesOrder:
    sales_order = db.scalar(
        select(SalesOrder).where(
            SalesOrder.id == sales_order_id,
            SalesOrder.is_deleted.is_(False),
        )
    )
    if not sales_order:
        raise ProductionBusinessRuleError("SalesOrder not found")
    return sales_order


def _get_route_card(db: Session, route_card_id: int) -> RouteCard:
    route_card = db.scalar(
        select(RouteCard).where(
            RouteCard.id == route_card_id,
            RouteCard.is_deleted.is_(False),
        )
    )
    if not route_card:
        raise ProductionBusinessRuleError("RouteCard not found")
    return route_card


def _get_production_order(db: Session, production_order_id: int) -> ProductionOrder:
    production_order = db.scalar(
        select(ProductionOrder).where(
            ProductionOrder.id == production_order_id,
            ProductionOrder.is_deleted.is_(False),
        )
    )
    if not production_order:
        raise ProductionBusinessRuleError("ProductionOrder not found")
    return production_order


def _get_production_operation(db: Session, production_operation_id: int) -> ProductionOperation:
    operation = db.scalar(
        select(ProductionOperation).where(
            ProductionOperation.id == production_operation_id,
            ProductionOperation.is_deleted.is_(False),
        )
    )
    if not operation:
        raise ProductionBusinessRuleError("ProductionOperation not found")
    return operation


def _get_machine(db: Session, machine_id: int) -> Machine:
    machine = db.scalar(
        select(Machine).where(
            Machine.id == machine_id,
            Machine.is_deleted.is_(False),
        )
    )
    if not machine:
        raise ProductionBusinessRuleError("Machine not found")
    return machine


def _require_active_machine(db: Session, machine_id: int) -> Machine:
    machine = _get_machine(db, machine_id)
    if not machine.is_active:
        raise ProductionBusinessRuleError("Operation machine must be active")
    return machine


def _get_rework_order(db: Session, rework_order_id: int) -> ReworkOrder:
    rework_order = db.scalar(
        select(ReworkOrder).where(
            ReworkOrder.id == rework_order_id,
            ReworkOrder.is_deleted.is_(False),
        )
    )
    if not rework_order:
        raise ProductionBusinessRuleError("ReworkOrder not found")
    return rework_order


def _require_positive_quantity(value: Decimal, field_name: str) -> None:
    if value <= 0:
        raise ProductionBusinessRuleError(f"{field_name} must be greater than zero")


def _get_latest_inspection(db: Session, production_operation_id: int) -> InProcessInspection | None:
    return db.scalars(
        select(InProcessInspection)
        .where(
            InProcessInspection.production_operation_id == production_operation_id,
            InProcessInspection.is_deleted.is_(False),
        )
        .order_by(
            func.coalesce(InProcessInspection.inspection_time, InProcessInspection.created_at).desc(),
            InProcessInspection.id.desc(),
        )
    ).first()


def _build_rework_order(
    *,
    production_operation_id: int,
    reason: str,
    created_by: int | None,
) -> ReworkOrder:
    return ReworkOrder(
        production_operation_id=production_operation_id,
        reason=reason,
        status=ReworkOrderStatus.OPEN,
        created_by=created_by,
        updated_by=created_by,
    )


def _get_previous_incomplete_operation(db: Session, operation: ProductionOperation) -> ProductionOperation | None:
    return db.scalars(
        select(ProductionOperation)
        .where(
            ProductionOperation.production_order_id == operation.production_order_id,
            ProductionOperation.is_deleted.is_(False),
            ProductionOperation.operation_number < operation.operation_number,
            ProductionOperation.status != ProductionOperationStatus.COMPLETED,
        )
        .order_by(ProductionOperation.operation_number.asc(), ProductionOperation.id.asc())
    ).first()


def _get_production_order_logged_total(db: Session, production_order_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(ProductionLog.produced_quantity + ProductionLog.scrap_quantity), 0)).where(
            ProductionLog.production_order_id == production_order_id,
            ProductionLog.is_deleted.is_(False),
        )
    )
    return _to_decimal(total or 0)


def _has_open_rework_orders(db: Session, production_order_id: int) -> bool:
    open_rework_order_id = db.scalar(
        select(ReworkOrder.id)
        .join(ProductionOperation, ProductionOperation.id == ReworkOrder.production_operation_id)
        .where(
            ProductionOperation.production_order_id == production_order_id,
            ProductionOperation.is_deleted.is_(False),
            ReworkOrder.is_deleted.is_(False),
            ReworkOrder.status != ReworkOrderStatus.CLOSED,
        )
    )
    return open_rework_order_id is not None


def _is_production_order_ready_for_completion(db: Session, production_order: ProductionOrder) -> bool:
    planned_quantity = _to_decimal(production_order.planned_quantity)
    logged_total = _get_production_order_logged_total(db, production_order.id)
    return logged_total == planned_quantity and not _has_open_rework_orders(db, production_order.id)


def _create_fai_trigger_if_applicable(
    db: Session,
    *,
    production_order: ProductionOrder,
    operation: ProductionOperation,
    created_by: int | None,
) -> FAITrigger | None:
    if operation.status != ProductionOperationStatus.COMPLETED:
        return None

    first_operation_number = db.scalar(
        select(func.min(ProductionOperation.operation_number)).where(
            ProductionOperation.production_order_id == production_order.id,
            ProductionOperation.is_deleted.is_(False),
        )
    )
    if first_operation_number is None or operation.operation_number != int(first_operation_number):
        return None

    existing_trigger = db.scalar(
        select(FAITrigger).where(
            FAITrigger.production_order_id == production_order.id,
            FAITrigger.operation_id == operation.id,
            FAITrigger.is_deleted.is_(False),
        )
    )
    if existing_trigger:
        return existing_trigger

    fai_trigger = FAITrigger(
        production_order_id=production_order.id,
        operation_id=operation.id,
        triggered_at=_utc_now(),
        status=FAITriggerStatus.PENDING,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(fai_trigger)
    return fai_trigger


def create_production_order(
    db: Session,
    *,
    production_order_number: str,
    sales_order_id: int,
    route_card_id: int,
    planned_quantity: Decimal,
    due_date: date,
    start_date: date | None = None,
    created_by: int | None = None,
) -> ProductionOrder:
    normalized_number = production_order_number.strip()
    if not normalized_number:
        raise ProductionBusinessRuleError("Production order number is required")

    planned_quantity = _to_decimal(planned_quantity)
    _require_positive_quantity(planned_quantity, "planned_quantity")

    if start_date is not None and due_date < start_date:
        raise ProductionBusinessRuleError("due_date must be on or after start_date")

    existing_order = db.scalar(
        select(ProductionOrder).where(
            ProductionOrder.production_order_number == normalized_number,
            ProductionOrder.is_deleted.is_(False),
        )
    )
    if existing_order:
        raise ProductionBusinessRuleError("Production order number already exists")

    _get_sales_order(db, sales_order_id)
    route_card = _get_route_card(db, route_card_id)

    if route_card.status != RouteCardStatus.RELEASED:
        raise ProductionBusinessRuleError("ProductionOrder cannot be created unless RouteCard status is Released")

    if route_card.sales_order_id != sales_order_id:
        raise ProductionBusinessRuleError("RouteCard does not belong to the selected SalesOrder")

    production_order = ProductionOrder(
        production_order_number=normalized_number,
        sales_order_id=sales_order_id,
        route_card_id=route_card_id,
        planned_quantity=planned_quantity,
        status=ProductionOrderStatus.DRAFT,
        start_date=start_date,
        due_date=due_date,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(production_order)
    db.commit()
    db.refresh(production_order)
    return production_order


def list_production_orders(
    db: Session,
    *,
    q: str | None = None,
    status_filter: ProductionOrderStatus | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[ProductionOrder]:
    stmt = select(ProductionOrder).where(ProductionOrder.is_deleted.is_(False))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(ProductionOrder.production_order_number.ilike(pattern))
    if status_filter is not None:
        stmt = stmt.where(ProductionOrder.status == status_filter)

    return db.scalars(
        stmt.order_by(ProductionOrder.id.desc()).offset(skip).limit(limit)
    ).all()


def get_production_order(
    db: Session,
    *,
    production_order_id: int,
) -> ProductionOrder:
    production_order = db.scalar(
        select(ProductionOrder)
        .options(
            selectinload(ProductionOrder.operations).selectinload(ProductionOperation.machine),
            selectinload(ProductionOrder.fai_triggers),
            selectinload(ProductionOrder.logs),
        )
        .where(
            ProductionOrder.id == production_order_id,
            ProductionOrder.is_deleted.is_(False),
        )
    )
    if not production_order:
        raise ProductionBusinessRuleError("ProductionOrder not found")
    return production_order


def release_production_order(
    db: Session,
    *,
    production_order_id: int,
    released_by: int | None = None,
) -> ProductionOrder:
    production_order = _get_production_order(db, production_order_id)
    route_card = _get_route_card(db, production_order.route_card_id)

    if route_card.status != RouteCardStatus.RELEASED:
        raise ProductionBusinessRuleError("ProductionOrder cannot be released unless RouteCard status is Released")

    if production_order.status != ProductionOrderStatus.DRAFT:
        raise ProductionBusinessRuleError("ProductionOrder can be released only from Draft status")

    production_order.status = ProductionOrderStatus.RELEASED
    production_order.updated_by = released_by
    db.add(production_order)
    db.commit()
    db.refresh(production_order)
    return production_order


def start_production_order(
    db: Session,
    *,
    production_order_id: int,
    started_by: int | None = None,
) -> ProductionOrder:
    production_order = _get_production_order(db, production_order_id)
    route_card = _get_route_card(db, production_order.route_card_id)

    if route_card.status != RouteCardStatus.RELEASED:
        raise ProductionBusinessRuleError("ProductionOrder cannot start unless RouteCard status is Released")

    if production_order.status == ProductionOrderStatus.DRAFT:
        raise ProductionBusinessRuleError("ProductionOrder must be Released before it can be started")

    if production_order.status == ProductionOrderStatus.COMPLETED:
        raise ProductionBusinessRuleError("Completed ProductionOrder cannot be started again")

    if production_order.status == ProductionOrderStatus.RELEASED:
        production_order.status = ProductionOrderStatus.IN_PROGRESS
        if production_order.start_date is None:
            production_order.start_date = _utc_now().date()
        production_order.updated_by = started_by
        db.add(production_order)
        db.commit()
        db.refresh(production_order)

    return production_order


def complete_production_order(
    db: Session,
    *,
    production_order_id: int,
    completed_by: int | None = None,
) -> ProductionOrder:
    production_order = _get_production_order(db, production_order_id)

    if production_order.status == ProductionOrderStatus.DRAFT:
        raise ProductionBusinessRuleError("Draft ProductionOrder cannot be completed")
    if production_order.status == ProductionOrderStatus.COMPLETED:
        raise ProductionBusinessRuleError("ProductionOrder is already completed")

    incomplete_operation = db.scalar(
        select(ProductionOperation.id).where(
            ProductionOperation.production_order_id == production_order.id,
            ProductionOperation.is_deleted.is_(False),
            ProductionOperation.status != ProductionOperationStatus.COMPLETED,
        )
    )
    if incomplete_operation:
        raise ProductionBusinessRuleError("ProductionOrder cannot be completed until all operations are completed")

    if _has_open_rework_orders(db, production_order.id):
        raise ProductionBusinessRuleError("ProductionOrder cannot be completed while open ReworkOrder exists")

    logged_total = _get_production_order_logged_total(db, production_order.id)
    planned_quantity = _to_decimal(production_order.planned_quantity)
    if logged_total != planned_quantity:
        raise ProductionBusinessRuleError(
            "ProductionOrder cannot be completed until produced and scrap quantities reconcile with planned quantity"
        )

    production_order.status = ProductionOrderStatus.COMPLETED
    if production_order.start_date is None:
        production_order.start_date = _utc_now().date()
    production_order.updated_by = completed_by
    db.add(production_order)
    db.commit()
    db.refresh(production_order)
    return production_order


def start_operation(
    db: Session,
    *,
    production_operation_id: int,
    started_by: int | None = None,
) -> ProductionOperation:
    operation = _get_production_operation(db, production_operation_id)
    production_order = _get_production_order(db, operation.production_order_id)
    route_card = _get_route_card(db, production_order.route_card_id)

    if route_card.status != RouteCardStatus.RELEASED:
        raise ProductionBusinessRuleError("Operation cannot start unless RouteCard status is Released")

    if production_order.status == ProductionOrderStatus.DRAFT:
        raise ProductionBusinessRuleError("ProductionOrder must be Released before operations can start")

    if production_order.status == ProductionOrderStatus.COMPLETED:
        raise ProductionBusinessRuleError("Operation cannot start on a completed ProductionOrder")

    if operation.status == ProductionOperationStatus.COMPLETED:
        raise ProductionBusinessRuleError("Completed operation cannot be started again")

    if operation.machine_id is not None:
        _require_active_machine(db, operation.machine_id)

    previous_incomplete_operation = _get_previous_incomplete_operation(db, operation)
    if previous_incomplete_operation is not None:
        raise ProductionBusinessRuleError(
            f"Operation {operation.operation_number} cannot start before operation "
            f"{previous_incomplete_operation.operation_number} is completed"
        )

    if operation.status == ProductionOperationStatus.PENDING:
        operation.status = ProductionOperationStatus.IN_PROGRESS
        operation.started_at = _utc_now()
        operation.updated_by = started_by

    if production_order.status in (ProductionOrderStatus.DRAFT, ProductionOrderStatus.RELEASED):
        production_order.status = ProductionOrderStatus.IN_PROGRESS
        if production_order.start_date is None:
            production_order.start_date = _utc_now().date()
        production_order.updated_by = started_by
        db.add(production_order)

    db.add(operation)
    db.commit()
    db.refresh(operation)
    return operation


def assign_operator_to_operation(
    db: Session,
    *,
    production_operation_id: int,
    operator_user_id: int,
    assigned_by: int | None = None,
) -> OperationOperator:
    _get_production_operation(db, production_operation_id)
    _get_production_operator_user(db, operator_user_id)

    existing_assignment = db.scalar(
        select(OperationOperator).where(
            OperationOperator.production_operation_id == production_operation_id,
            OperationOperator.operator_user_id == operator_user_id,
            OperationOperator.is_deleted.is_(False),
        )
    )
    if existing_assignment:
        return existing_assignment

    assignment = OperationOperator(
        production_operation_id=production_operation_id,
        operator_user_id=operator_user_id,
        assigned_at=_utc_now(),
        created_by=assigned_by,
        updated_by=assigned_by,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def create_machine(
    db: Session,
    *,
    machine_code: str,
    machine_name: str,
    work_center: str,
    is_active: bool = True,
    created_by: int | None = None,
) -> Machine:
    normalized_code = machine_code.strip()
    normalized_name = machine_name.strip()
    normalized_work_center = work_center.strip()

    if not normalized_code:
        raise ProductionBusinessRuleError("machine_code is required")
    if not normalized_name:
        raise ProductionBusinessRuleError("machine_name is required")
    if not normalized_work_center:
        raise ProductionBusinessRuleError("work_center is required")

    existing_machine = db.scalar(
        select(Machine).where(
            Machine.machine_code == normalized_code,
            Machine.is_deleted.is_(False),
        )
    )
    if existing_machine:
        raise ProductionBusinessRuleError("Machine code already exists")

    machine = Machine(
        machine_code=normalized_code,
        machine_name=normalized_name,
        work_center=normalized_work_center,
        is_active=is_active,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


def list_machines(
    db: Session,
    *,
    q: str | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[Machine]:
    stmt = select(Machine).where(Machine.is_deleted.is_(False))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Machine.machine_code.ilike(pattern),
                Machine.machine_name.ilike(pattern),
                Machine.work_center.ilike(pattern),
            )
        )
    if is_active is not None:
        stmt = stmt.where(Machine.is_active.is_(is_active))

    return db.scalars(
        stmt.order_by(Machine.id.desc()).offset(skip).limit(limit)
    ).all()


def create_rework_order(
    db: Session,
    *,
    production_operation_id: int,
    reason: str,
    created_by: int | None = None,
) -> ReworkOrder:
    _get_production_operation(db, production_operation_id)

    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ProductionBusinessRuleError("Rework reason is required")

    rework_order = _build_rework_order(
        production_operation_id=production_operation_id,
        reason=normalized_reason,
        created_by=created_by,
    )
    db.add(rework_order)
    db.commit()
    db.refresh(rework_order)
    return rework_order


def close_rework_order(
    db: Session,
    *,
    rework_order_id: int,
    closed_by: int | None = None,
) -> ReworkOrder:
    rework_order = _get_rework_order(db, rework_order_id)

    if rework_order.status == ReworkOrderStatus.CLOSED:
        raise ProductionBusinessRuleError("ReworkOrder is already closed")

    latest_inspection = _get_latest_inspection(db, rework_order.production_operation_id)
    if not latest_inspection or latest_inspection.inspection_result != InspectionResult.PASS:
        raise ProductionBusinessRuleError("ReworkOrder cannot be closed until latest inspection result is Pass")

    rework_order.status = ReworkOrderStatus.CLOSED
    rework_order.updated_by = closed_by
    db.add(rework_order)
    db.commit()
    db.refresh(rework_order)
    return rework_order


def record_inprocess_inspection(
    db: Session,
    *,
    production_operation_id: int,
    inspection_result: InspectionResult,
    inspected_by: int | None = None,
    remarks: str | None = None,
    inspection_time: datetime | None = None,
    created_by: int | None = None,
) -> tuple[InProcessInspection, ReworkOrder | None]:
    _get_production_operation(db, production_operation_id)

    if inspected_by is not None:
        _get_user(db, inspected_by)

    normalized_remarks = remarks.strip() if remarks else None
    effective_inspection_time = inspection_time
    if inspection_result != InspectionResult.PENDING and effective_inspection_time is None:
        effective_inspection_time = _utc_now()

    inspection = InProcessInspection(
        production_operation_id=production_operation_id,
        inspected_by=inspected_by,
        inspection_result=inspection_result,
        remarks=normalized_remarks,
        inspection_time=effective_inspection_time,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(inspection)

    rework_order: ReworkOrder | None = None
    if inspection_result == InspectionResult.FAIL:
        rework_reason = normalized_remarks or "Auto-created from failed in-process inspection"
        rework_order = _build_rework_order(
            production_operation_id=production_operation_id,
            reason=rework_reason,
            created_by=created_by,
        )
        db.add(rework_order)

    db.commit()
    db.refresh(inspection)
    if rework_order is not None:
        db.refresh(rework_order)
    return inspection, rework_order


def complete_operation(
    db: Session,
    *,
    production_operation_id: int,
    completed_by: int | None = None,
) -> tuple[ProductionOperation, FAITrigger | None]:
    operation = _get_production_operation(db, production_operation_id)
    production_order = _get_production_order(db, operation.production_order_id)

    if operation.status == ProductionOperationStatus.COMPLETED:
        raise ProductionBusinessRuleError("Operation is already completed")

    if operation.started_at is None:
        raise ProductionBusinessRuleError("Operation must be started before completion")

    latest_inspection = _get_latest_inspection(db, production_operation_id)
    if not latest_inspection:
        raise ProductionBusinessRuleError("Operation cannot be completed without in-process inspection")

    if latest_inspection.inspection_result != InspectionResult.PASS:
        raise ProductionBusinessRuleError("Operation cannot be completed unless inspection result is Pass")

    operation.status = ProductionOperationStatus.COMPLETED
    operation.completed_at = _utc_now()
    operation.updated_by = completed_by
    db.add(operation)

    remaining_open_operation = db.scalar(
        select(ProductionOperation.id).where(
            ProductionOperation.production_order_id == production_order.id,
            ProductionOperation.id != operation.id,
            ProductionOperation.is_deleted.is_(False),
            ProductionOperation.status != ProductionOperationStatus.COMPLETED,
        )
    )

    if remaining_open_operation:
        production_order.status = ProductionOrderStatus.IN_PROGRESS
    elif _is_production_order_ready_for_completion(db, production_order):
        production_order.status = ProductionOrderStatus.COMPLETED
    else:
        production_order.status = ProductionOrderStatus.IN_PROGRESS
    production_order.updated_by = completed_by
    db.add(production_order)

    fai_trigger = _create_fai_trigger_if_applicable(
        db,
        production_order=production_order,
        operation=operation,
        created_by=completed_by,
    )

    db.commit()
    db.refresh(operation)
    if fai_trigger is not None:
        db.refresh(fai_trigger)
    return operation, fai_trigger


def record_production_log(
    db: Session,
    *,
    production_order_id: int,
    operation_id: int,
    batch_number: str | None = None,
    operator_user_id: int | None = None,
    machine_id: int | None = None,
    produced_quantity: Decimal,
    scrap_quantity: Decimal,
    scrap_reason: str | None = None,
    shift: str | None = None,
    recorded_by: int,
    created_by: int | None = None,
    recorded_at: datetime | None = None,
) -> ProductionLog:
    production_order = _get_production_order(db, production_order_id)
    operation = _get_production_operation(db, operation_id)
    recording_user = _get_user(db, recorded_by)

    if operation.production_order_id != production_order.id:
        raise ProductionBusinessRuleError("Operation does not belong to the selected ProductionOrder")

    normalized_batch_number = (batch_number or production_order.production_order_number).strip()
    if not normalized_batch_number:
        raise ProductionBusinessRuleError("batch_number is required")

    resolved_operator_user_id = operator_user_id
    if resolved_operator_user_id is not None:
        _get_production_operator_user(db, resolved_operator_user_id)
    elif _user_has_role(db, recording_user, "Production"):
        resolved_operator_user_id = recording_user.id

    resolved_machine_id = machine_id if machine_id is not None else operation.machine_id
    if resolved_machine_id is not None:
        _get_machine(db, resolved_machine_id)

    produced_quantity = _to_decimal(produced_quantity)
    scrap_quantity = _to_decimal(scrap_quantity)

    if produced_quantity < 0:
        raise ProductionBusinessRuleError("produced_quantity cannot be negative")
    if scrap_quantity < 0:
        raise ProductionBusinessRuleError("scrap_quantity cannot be negative")
    if produced_quantity + scrap_quantity <= 0:
        raise ProductionBusinessRuleError("At least one of produced_quantity or scrap_quantity must be greater than zero")

    existing_total_decimal = _get_production_order_logged_total(db, production_order_id)
    new_total = existing_total_decimal + produced_quantity + scrap_quantity
    planned_quantity = _to_decimal(production_order.planned_quantity)

    if new_total > planned_quantity:
        raise ProductionBusinessRuleError("Production log exceeds planned quantity")

    if resolved_machine_id is not None:
        _require_active_machine(db, resolved_machine_id)

    log = ProductionLog(
        production_order_id=production_order_id,
        operation_id=operation_id,
        batch_number=normalized_batch_number,
        operator_user_id=resolved_operator_user_id,
        machine_id=resolved_machine_id,
        produced_quantity=produced_quantity,
        scrap_quantity=scrap_quantity,
        scrap_reason=scrap_reason.strip() if scrap_reason else None,
        shift=shift.strip() if shift else None,
        recorded_by=recorded_by,
        recorded_at=recorded_at or _utc_now(),
        created_by=created_by if created_by is not None else recorded_by,
        updated_by=created_by if created_by is not None else recorded_by,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def trigger_fai(
    db: Session,
    *,
    production_order_id: int,
    operation_id: int,
    created_by: int | None = None,
) -> FAITrigger | None:
    production_order = _get_production_order(db, production_order_id)
    operation = _get_production_operation(db, operation_id)

    if operation.production_order_id != production_order.id:
        raise ProductionBusinessRuleError("Operation does not belong to the selected ProductionOrder")

    fai_trigger = _create_fai_trigger_if_applicable(
        db,
        production_order=production_order,
        operation=operation,
        created_by=created_by,
    )
    if fai_trigger is None:
        return None

    db.commit()
    db.refresh(fai_trigger)
    return fai_trigger
