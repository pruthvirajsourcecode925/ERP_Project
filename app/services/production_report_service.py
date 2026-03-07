from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.modules.production.models import (
    Machine,
    ProductionLog,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
)
from app.services.production_service import ProductionBusinessRuleError


def _to_decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_date_range(*, start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ProductionBusinessRuleError("end_date must be greater than or equal to start_date")


def _apply_log_date_filters(statement, *, start_date: date, end_date: date):
    return statement.where(
        ProductionLog.is_deleted.is_(False),
        func.date(ProductionLog.recorded_at) >= start_date,
        func.date(ProductionLog.recorded_at) <= end_date,
    )


def get_batch_production_report(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    batch_number: str | None = None,
) -> list[dict]:
    _validate_date_range(start_date=start_date, end_date=end_date)

    totals_stmt = (
        select(
            ProductionLog.batch_number,
            func.coalesce(func.sum(ProductionLog.produced_quantity), 0).label("total_produced_quantity"),
            func.coalesce(func.sum(ProductionLog.scrap_quantity), 0).label("total_scrap_quantity"),
        )
        .select_from(ProductionLog)
        .group_by(ProductionLog.batch_number)
    )
    totals_stmt = _apply_log_date_filters(totals_stmt, start_date=start_date, end_date=end_date)
    if batch_number:
        totals_stmt = totals_stmt.where(ProductionLog.batch_number == batch_number.strip())

    totals_rows = db.execute(totals_stmt.order_by(ProductionLog.batch_number.asc())).all()
    if not totals_rows:
        return []

    target_batches = [row.batch_number for row in totals_rows]

    machine_stmt = (
        select(
            ProductionLog.batch_number,
            Machine.id,
            Machine.machine_code,
            Machine.machine_name,
        )
        .select_from(ProductionLog)
        .join(Machine, Machine.id == ProductionLog.machine_id)
        .distinct()
        .where(ProductionLog.batch_number.in_(target_batches), Machine.is_deleted.is_(False))
    )
    machine_stmt = _apply_log_date_filters(machine_stmt, start_date=start_date, end_date=end_date)
    machine_rows = db.execute(machine_stmt).all()

    operator_stmt = (
        select(
            ProductionLog.batch_number,
            User.id,
            User.username,
            User.email,
        )
        .select_from(ProductionLog)
        .join(User, User.id == ProductionLog.operator_user_id)
        .distinct()
        .where(ProductionLog.batch_number.in_(target_batches), User.is_deleted.is_(False))
    )
    operator_stmt = _apply_log_date_filters(operator_stmt, start_date=start_date, end_date=end_date)
    operator_rows = db.execute(operator_stmt).all()

    machines_by_batch: dict[str, list[dict]] = {batch: [] for batch in target_batches}
    for row in machine_rows:
        machines_by_batch[row.batch_number].append(
            {
                "id": row.id,
                "machine_code": row.machine_code,
                "machine_name": row.machine_name,
            }
        )

    operators_by_batch: dict[str, list[dict]] = {batch: [] for batch in target_batches}
    for row in operator_rows:
        operators_by_batch[row.batch_number].append(
            {
                "id": row.id,
                "username": row.username,
                "email": row.email,
            }
        )

    return [
        {
            "batch_number": row.batch_number,
            "total_produced_quantity": _to_decimal(row.total_produced_quantity),
            "total_scrap_quantity": _to_decimal(row.total_scrap_quantity),
            "machines_used": machines_by_batch.get(row.batch_number, []),
            "operators_involved": operators_by_batch.get(row.batch_number, []),
        }
        for row in totals_rows
    ]


def get_operator_activity_report(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    operator_id: int | None = None,
) -> list[dict]:
    _validate_date_range(start_date=start_date, end_date=end_date)

    completed_operation_id = case(
        (ProductionOperation.status == ProductionOperationStatus.COMPLETED, ProductionOperation.id),
        else_=None,
    )
    stmt = (
        select(
            User.id,
            User.username,
            User.email,
            func.count(func.distinct(ProductionLog.production_order_id)).label("jobs_worked"),
            func.count(func.distinct(completed_operation_id)).label("operations_completed"),
            func.coalesce(func.sum(ProductionLog.produced_quantity), 0).label("total_quantity_produced"),
            func.coalesce(func.sum(ProductionLog.scrap_quantity), 0).label("total_scrap"),
        )
        .select_from(ProductionLog)
        .join(User, User.id == ProductionLog.operator_user_id)
        .join(ProductionOrder, ProductionOrder.id == ProductionLog.production_order_id)
        .join(ProductionOperation, ProductionOperation.id == ProductionLog.operation_id)
        .where(User.is_deleted.is_(False), ProductionOrder.is_deleted.is_(False), ProductionOperation.is_deleted.is_(False))
        .group_by(User.id, User.username, User.email)
        .order_by(User.username.asc())
    )
    stmt = _apply_log_date_filters(stmt, start_date=start_date, end_date=end_date)
    if operator_id is not None:
        stmt = stmt.where(ProductionLog.operator_user_id == operator_id)

    rows = db.execute(stmt).all()
    return [
        {
            "operator": {
                "id": row.id,
                "username": row.username,
                "email": row.email,
            },
            "jobs_worked": row.jobs_worked,
            "operations_completed": row.operations_completed,
            "total_quantity_produced": _to_decimal(row.total_quantity_produced),
            "total_scrap": _to_decimal(row.total_scrap),
        }
        for row in rows
    ]


def get_machine_utilization_report(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    machine_id: int | None = None,
) -> list[dict]:
    _validate_date_range(start_date=start_date, end_date=end_date)

    stmt = (
        select(
            Machine.id,
            Machine.machine_code,
            Machine.machine_name,
            Machine.work_center,
            func.count(func.distinct(ProductionLog.operation_id)).label("total_operations"),
            func.coalesce(func.sum(ProductionLog.produced_quantity), 0).label("production_quantity"),
            func.coalesce(func.sum(ProductionLog.scrap_quantity), 0).label("scrap_quantity"),
        )
        .select_from(ProductionLog)
        .join(Machine, Machine.id == ProductionLog.machine_id)
        .join(ProductionOperation, ProductionOperation.id == ProductionLog.operation_id)
        .where(Machine.is_deleted.is_(False), ProductionOperation.is_deleted.is_(False))
        .group_by(Machine.id, Machine.machine_code, Machine.machine_name, Machine.work_center)
        .order_by(Machine.machine_code.asc())
    )
    stmt = _apply_log_date_filters(stmt, start_date=start_date, end_date=end_date)
    if machine_id is not None:
        stmt = stmt.where(ProductionLog.machine_id == machine_id)

    rows = db.execute(stmt).all()
    if not rows:
        return []

    target_machine_ids = [row.id for row in rows]
    operator_stmt = (
        select(
            ProductionLog.machine_id,
            User.id,
            User.username,
            User.email,
        )
        .select_from(ProductionLog)
        .join(User, User.id == ProductionLog.operator_user_id)
        .distinct()
        .where(
            ProductionLog.machine_id.in_(target_machine_ids),
            User.is_deleted.is_(False),
        )
    )
    operator_stmt = _apply_log_date_filters(operator_stmt, start_date=start_date, end_date=end_date)
    operator_rows = db.execute(operator_stmt).all()

    operators_by_machine: dict[int, list[dict]] = {machine_key: [] for machine_key in target_machine_ids}
    for row in operator_rows:
        if row.machine_id is None:
            continue
        operators_by_machine[row.machine_id].append(
            {
                "id": row.id,
                "username": row.username,
                "email": row.email,
            }
        )

    return [
        {
            "machine": {
                "id": row.id,
                "machine_code": row.machine_code,
                "machine_name": row.machine_name,
                "work_center": row.work_center,
            },
            "total_operations": row.total_operations,
            "production_quantity": _to_decimal(row.production_quantity),
            "scrap_quantity": _to_decimal(row.scrap_quantity),
            "operators_used": operators_by_machine.get(row.id, []),
        }
        for row in rows
    ]


def get_job_progress_report(
    db: Session,
    *,
    production_order_id: int,
) -> dict:
    production_order = db.scalar(
        select(ProductionOrder).where(
            ProductionOrder.id == production_order_id,
            ProductionOrder.is_deleted.is_(False),
        )
    )
    if not production_order:
        raise ProductionBusinessRuleError("ProductionOrder not found")

    totals_row = db.execute(
        select(
            func.coalesce(func.sum(ProductionLog.produced_quantity), 0).label("produced_quantity"),
            func.coalesce(func.sum(ProductionLog.scrap_quantity), 0).label("scrap_quantity"),
        ).where(
            ProductionLog.production_order_id == production_order_id,
            ProductionLog.is_deleted.is_(False),
        )
    ).one()

    counts_row = db.execute(
        select(
            func.count(
                case(
                    (ProductionOperation.status == ProductionOperationStatus.COMPLETED, 1),
                    else_=None,
                )
            ).label("operations_completed"),
            func.count(
                case(
                    (ProductionOperation.status != ProductionOperationStatus.COMPLETED, 1),
                    else_=None,
                )
            ).label("operations_pending"),
        ).where(
            ProductionOperation.production_order_id == production_order_id,
            ProductionOperation.is_deleted.is_(False),
        )
    ).one()

    produced_quantity = _to_decimal(totals_row.produced_quantity)
    scrap_quantity = _to_decimal(totals_row.scrap_quantity)
    planned_quantity = _to_decimal(production_order.planned_quantity)

    return {
        "job_number": production_order.production_order_number,
        "planned_quantity": planned_quantity,
        "produced_quantity": produced_quantity,
        "scrap_quantity": scrap_quantity,
        "remaining_quantity": planned_quantity - produced_quantity - scrap_quantity,
        "operations_completed": counts_row.operations_completed,
        "operations_pending": counts_row.operations_pending,
    }
