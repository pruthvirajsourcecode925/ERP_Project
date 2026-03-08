from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.modules.dispatch.models import DispatchOrder
from app.modules.maintenance.models import MachineDowntime, MaintenanceMachine
from app.modules.production.models import InProcessInspection, InspectionResult, Machine, ProductionLog, ProductionOperation, ReworkOrder
from app.modules.purchase.models import PurchaseOrder, Supplier
from app.modules.quality.models import FinalInspection, IncomingInspection, IncomingInspectionStatus, QualityInspectionResult
from app.modules.stores.models import GRN, GRNItem


def _normalize_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _number(value: Decimal | int | float | None) -> int | float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return int(normalized)
        return float(round(value, 3))
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _hours_between(started_at: datetime | None, ended_at: datetime | None) -> float:
    if started_at is None or ended_at is None or ended_at <= started_at:
        return 0.0
    return round((ended_at - started_at).total_seconds() / 3600, 2)


def get_production_trend(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            func.date(ProductionLog.recorded_at).label("production_date"),
            func.coalesce(func.sum(ProductionLog.produced_quantity), 0).label("quantity"),
        )
        .where(ProductionLog.is_deleted.is_(False))
        .group_by(func.date(ProductionLog.recorded_at))
        .order_by(func.date(ProductionLog.recorded_at).asc())
    ).all()

    return [
        {
            "date": _normalize_date(row.production_date),
            "quantity": _number(row.quantity),
        }
        for row in rows
    ]


def get_quality_distribution(db: Session) -> dict[str, int]:
    inprocess_counts = db.execute(
        select(InProcessInspection.inspection_result, func.count(InProcessInspection.id))
        .where(InProcessInspection.is_deleted.is_(False))
        .group_by(InProcessInspection.inspection_result)
    ).all()
    final_counts = db.execute(
        select(FinalInspection.result, func.count(FinalInspection.id))
        .where(FinalInspection.is_deleted.is_(False))
        .group_by(FinalInspection.result)
    ).all()
    incoming_counts = db.execute(
        select(IncomingInspection.status, func.count(IncomingInspection.id))
        .where(IncomingInspection.is_deleted.is_(False))
        .group_by(IncomingInspection.status)
    ).all()
    rework_count = db.scalar(
        select(func.count(ReworkOrder.id)).where(ReworkOrder.is_deleted.is_(False))
    )

    passed = 0
    failed = 0

    for result, count in inprocess_counts:
        if result == InspectionResult.PASS:
            passed += int(count or 0)
        elif result == InspectionResult.FAIL:
            failed += int(count or 0)

    for result, count in final_counts:
        if result == QualityInspectionResult.PASS:
            passed += int(count or 0)
        elif result == QualityInspectionResult.FAIL:
            failed += int(count or 0)

    for status, count in incoming_counts:
        if status == IncomingInspectionStatus.ACCEPTED:
            passed += int(count or 0)
        elif status == IncomingInspectionStatus.REJECTED:
            failed += int(count or 0)

    return {
        "pass": passed,
        "fail": failed,
        "rework": int(rework_count or 0),
    }


def get_dispatch_trend(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            DispatchOrder.dispatch_date.label("dispatch_date"),
            func.count(DispatchOrder.id).label("dispatch_count"),
        )
        .where(DispatchOrder.is_deleted.is_(False))
        .group_by(DispatchOrder.dispatch_date)
        .order_by(DispatchOrder.dispatch_date.asc())
    ).all()

    return [
        {
            "date": _normalize_date(row.dispatch_date),
            "dispatch_count": int(row.dispatch_count or 0),
        }
        for row in rows
    ]


def get_supplier_performance(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            Supplier.id.label("supplier_id"),
            Supplier.supplier_name.label("supplier_name"),
            PurchaseOrder.id.label("purchase_order_id"),
            PurchaseOrder.expected_delivery_date.label("expected_delivery_date"),
            func.min(GRN.grn_date).label("first_grn_date"),
            func.coalesce(func.sum(GRNItem.rejected_quantity), 0).label("rejected_quantity"),
        )
        .select_from(Supplier)
        .outerjoin(
            PurchaseOrder,
            (PurchaseOrder.supplier_id == Supplier.id) & (PurchaseOrder.is_deleted.is_(False)),
        )
        .outerjoin(GRN, (GRN.purchase_order_id == PurchaseOrder.id) & (GRN.is_deleted.is_(False)))
        .outerjoin(GRNItem, (GRNItem.grn_id == GRN.id) & (GRNItem.is_deleted.is_(False)))
        .where(Supplier.is_deleted.is_(False))
        .group_by(Supplier.id, Supplier.supplier_name, PurchaseOrder.id, PurchaseOrder.expected_delivery_date)
        .order_by(Supplier.supplier_name.asc(), PurchaseOrder.id.asc())
    ).all()

    performance: dict[int, dict[str, object]] = {}
    for row in rows:
        supplier_id = int(row.supplier_id)
        summary = performance.setdefault(
            supplier_id,
            {
                "supplier": row.supplier_name,
                "on_time": 0,
                "late": 0,
                "rejected": 0,
            },
        )
        if row.purchase_order_id is None:
            continue

        first_grn_date = row.first_grn_date
        expected_delivery_date = row.expected_delivery_date
        if first_grn_date is not None:
            if expected_delivery_date is None or first_grn_date <= expected_delivery_date:
                summary["on_time"] += 1
            else:
                summary["late"] += 1

        rejected_quantity = row.rejected_quantity
        if isinstance(rejected_quantity, Decimal):
            has_rejection = rejected_quantity > 0
        else:
            has_rejection = bool(rejected_quantity)
        if has_rejection:
            summary["rejected"] += 1

    return list(performance.values())


def get_machine_utilization(db: Session) -> list[dict[str, object]]:
    utilization: dict[str, dict[str, object]] = {}

    operation_rows = db.execute(
        select(
            Machine.machine_code,
            Machine.machine_name,
            ProductionOperation.started_at,
            ProductionOperation.completed_at,
        )
        .join(Machine, Machine.id == ProductionOperation.machine_id)
        .where(
            ProductionOperation.is_deleted.is_(False),
            Machine.is_deleted.is_(False),
        )
    ).all()

    for row in operation_rows:
        machine_label = row.machine_code or row.machine_name
        summary = utilization.setdefault(
            machine_label,
            {
                "machine": machine_label,
                "production_hours": 0.0,
                "downtime_hours": 0.0,
            },
        )
        summary["production_hours"] += _hours_between(row.started_at, row.completed_at)

    downtime_rows = db.execute(
        select(
            MaintenanceMachine.machine_code,
            MaintenanceMachine.machine_name,
            MachineDowntime.duration_minutes,
            MachineDowntime.downtime_start_at,
            MachineDowntime.downtime_end_at,
        )
        .join(MaintenanceMachine, MaintenanceMachine.id == MachineDowntime.machine_id)
        .where(
            MachineDowntime.is_deleted.is_(False),
            MaintenanceMachine.is_deleted.is_(False),
        )
    ).all()

    for row in downtime_rows:
        machine_label = row.machine_code or row.machine_name
        summary = utilization.setdefault(
            machine_label,
            {
                "machine": machine_label,
                "production_hours": 0.0,
                "downtime_hours": 0.0,
            },
        )
        if row.duration_minutes is not None:
            summary["downtime_hours"] += round(row.duration_minutes / 60, 2)
        else:
            summary["downtime_hours"] += _hours_between(row.downtime_start_at, row.downtime_end_at)

    return [
        {
            "machine": value["machine"],
            "production_hours": round(value["production_hours"], 2),
            "downtime_hours": round(value["downtime_hours"], 2),
        }
        for value in sorted(utilization.values(), key=lambda item: str(item["machine"]).lower())
    ]


def get_user_performance(db: Session) -> list[dict[str, object]]:
    production_rows = db.execute(
        select(ProductionLog.recorded_by, ProductionLog.production_order_id)
        .where(ProductionLog.is_deleted.is_(False))
    ).all()
    inprocess_rows = db.execute(
        select(InProcessInspection.inspected_by)
        .where(
            InProcessInspection.is_deleted.is_(False),
            InProcessInspection.inspected_by.is_not(None),
        )
    ).all()
    final_rows = db.execute(
        select(FinalInspection.inspected_by)
        .where(FinalInspection.is_deleted.is_(False))
    ).all()
    incoming_rows = db.execute(
        select(IncomingInspection.inspected_by)
        .where(IncomingInspection.is_deleted.is_(False))
    ).all()
    dispatch_rows = db.execute(
        select(DispatchOrder.created_by, DispatchOrder.released_by, DispatchOrder.id)
        .where(DispatchOrder.is_deleted.is_(False))
    ).all()

    users: dict[int, dict[str, object]] = {}

    def ensure_user(user_id: int | None, username: str | None = None) -> dict[str, object] | None:
        if user_id is None:
            return None
        summary = users.setdefault(
            int(user_id),
            {
                "user": username or f"User#{user_id}",
                "production_jobs": set(),
                "inspections": 0,
                "dispatches": set(),
            },
        )
        return summary

    for user_id, production_order_id in production_rows:
        summary = ensure_user(user_id)
        if summary is not None:
            summary["production_jobs"].add(int(production_order_id))

    for (user_id,) in inprocess_rows:
        summary = ensure_user(user_id)
        if summary is not None:
            summary["inspections"] += 1

    for (user_id,) in final_rows:
        summary = ensure_user(user_id)
        if summary is not None:
            summary["inspections"] += 1

    for (user_id,) in incoming_rows:
        summary = ensure_user(user_id)
        if summary is not None:
            summary["inspections"] += 1

    for created_by, released_by, dispatch_id in dispatch_rows:
        created_summary = ensure_user(created_by)
        if created_summary is not None:
            created_summary["dispatches"].add(int(dispatch_id))
        released_summary = ensure_user(released_by)
        if released_summary is not None:
            released_summary["dispatches"].add(int(dispatch_id))

    if not users:
        return []

    user_names = {
        user.id: user.username
        for user in db.scalars(select(User).where(User.id.in_(list(users.keys())), User.is_deleted.is_(False))).all()
    }

    results = []
    for user_id, summary in users.items():
        results.append(
            {
                "user": user_names.get(user_id, summary["user"]),
                "production_jobs": len(summary["production_jobs"]),
                "inspections": int(summary["inspections"]),
                "dispatches": len(summary["dispatches"]),
            }
        )

    return sorted(results, key=lambda item: str(item["user"]).lower())