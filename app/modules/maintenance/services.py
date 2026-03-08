from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.maintenance.models import (
    BreakdownReport,
    BreakdownSeverity,
    BreakdownStatus,
    DowntimeSourceType,
    MaintenanceMachine,
    MachineDowntime,
    MachineHistory,
    MachineHistoryEventType,
    MachineStatus,
    MaintenanceFrequencyType,
    MaintenanceWorkOrder,
    PMRecordStatus,
    PreventiveMaintenancePlan,
    PreventiveMaintenanceRecord,
    WorkOrderStatus,
)


class MaintenanceBusinessRuleError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utc_now().date()


def _field_value(data: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        return data.get(field_name, default)
    return getattr(data, field_name, default)


def _require_int(data: Any, field_name: str) -> int:
    value = _field_value(data, field_name)
    if value is None:
        raise MaintenanceBusinessRuleError(f"{field_name} is required")
    return int(value)


def _coerce_enum(value: Any, enum_cls: type, field_name: str):
    if isinstance(value, enum_cls):
        return value

    if isinstance(value, str):
        for member in enum_cls:
            if value == member.value or value == member.name:
                return member

    allowed = ", ".join(member.value for member in enum_cls)
    raise MaintenanceBusinessRuleError(f"{field_name} must be one of: {allowed}")


def _current_user_id(current_user: Any) -> int | None:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        return None
    return int(user_id)


def _get_machine(db: Session, machine_id: int) -> MaintenanceMachine:
    machine = db.scalar(
        select(MaintenanceMachine).where(
            MaintenanceMachine.id == machine_id,
            MaintenanceMachine.is_deleted.is_(False),
        )
    )
    if not machine:
        raise MaintenanceBusinessRuleError("Machine not found")
    return machine


def _get_plan(db: Session, plan_id: int) -> PreventiveMaintenancePlan:
    plan = db.scalar(
        select(PreventiveMaintenancePlan).where(
            PreventiveMaintenancePlan.id == plan_id,
            PreventiveMaintenancePlan.is_deleted.is_(False),
        )
    )
    if not plan:
        raise MaintenanceBusinessRuleError("Preventive maintenance plan not found")
    return plan


def _get_breakdown(db: Session, breakdown_id: int) -> BreakdownReport:
    breakdown = db.scalar(
        select(BreakdownReport).where(
            BreakdownReport.id == breakdown_id,
            BreakdownReport.is_deleted.is_(False),
        )
    )
    if not breakdown:
        raise MaintenanceBusinessRuleError("Breakdown report not found")
    return breakdown


def _get_work_order(db: Session, work_order_id: int) -> MaintenanceWorkOrder:
    work_order = db.scalar(
        select(MaintenanceWorkOrder).where(
            MaintenanceWorkOrder.id == work_order_id,
            MaintenanceWorkOrder.is_deleted.is_(False),
        )
    )
    if not work_order:
        raise MaintenanceBusinessRuleError("Work order not found")
    return work_order


def _next_due_by_frequency(base_date: date, frequency_type: MaintenanceFrequencyType, frequency_days: int | None) -> date | None:
    if frequency_type == MaintenanceFrequencyType.RUNTIME_BASED:
        return None

    days_map = {
        MaintenanceFrequencyType.DAILY: 1,
        MaintenanceFrequencyType.WEEKLY: 7,
        MaintenanceFrequencyType.MONTHLY: 30,
        MaintenanceFrequencyType.QUARTERLY: 90,
        MaintenanceFrequencyType.HALF_YEARLY: 182,
        MaintenanceFrequencyType.ANNUAL: 365,
    }
    interval_days = frequency_days or days_map.get(frequency_type)
    if not interval_days:
        return None
    return base_date + timedelta(days=int(interval_days))


def _add_status_history(
    db: Session,
    *,
    machine_id: int,
    previous_status: MachineStatus | None,
    new_status: MachineStatus,
    reason: str,
    user_id: int | None,
) -> None:
    db.add(
        MachineHistory(
            machine_id=machine_id,
            event_type=MachineHistoryEventType.STATUS_CHANGE,
            event_datetime=_utc_now(),
            previous_value=previous_status.value if previous_status else None,
            new_value=new_status.value,
            reason=reason,
            created_by=user_id,
            updated_by=user_id,
        )
    )


def _set_machine_status(db: Session, machine: MaintenanceMachine, new_status: MachineStatus, reason: str, user_id: int | None) -> None:
    previous_status = machine.status
    if previous_status == new_status:
        return

    machine.status = new_status
    machine.updated_by = user_id
    db.add(machine)
    _add_status_history(
        db,
        machine_id=machine.id,
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
        user_id=user_id,
    )


def create_machine(db: Session, data: Any, current_user: Any | None = None) -> MaintenanceMachine:
    user_id = _current_user_id(current_user)

    machine = MaintenanceMachine(
        machine_code=str(_field_value(data, "machine_code")),
        machine_name=str(_field_value(data, "machine_name")),
        work_center=str(_field_value(data, "work_center")),
        location=_field_value(data, "location"),
        manufacturer=_field_value(data, "manufacturer"),
        model=_field_value(data, "model"),
        serial_number=_field_value(data, "serial_number"),
        commissioned_date=_field_value(data, "commissioned_date"),
        status=_coerce_enum(
            _field_value(data, "status", MachineStatus.ACTIVE),
            MachineStatus,
            "status",
        ),
        created_by=user_id,
        updated_by=user_id,
    )

    db.add(machine)
    db.flush()

    db.add(
        MachineHistory(
            machine_id=machine.id,
            event_type=MachineHistoryEventType.INSTALLED,
            event_datetime=_utc_now(),
            previous_value=None,
            new_value=machine.status.value,
            reason="Machine created",
            created_by=user_id,
            updated_by=user_id,
        )
    )

    db.commit()
    db.refresh(machine)
    return machine


def create_preventive_plan(db: Session, data: Any, current_user: Any | None = None) -> PreventiveMaintenancePlan:
    user_id = _current_user_id(current_user)
    machine_id = _require_int(data, "machine_id")
    _get_machine(db, machine_id)

    plan = PreventiveMaintenancePlan(
        machine_id=machine_id,
        plan_code=str(_field_value(data, "plan_code")),
        frequency_type=_coerce_enum(_field_value(data, "frequency_type"), MaintenanceFrequencyType, "frequency_type"),
        frequency_days=_field_value(data, "frequency_days"),
        runtime_interval_hours=_field_value(data, "runtime_interval_hours"),
        checklist_template=_field_value(data, "checklist_template"),
        standard_reference=_field_value(data, "standard_reference"),
        next_due_date=_field_value(data, "next_due_date"),
        is_active=bool(_field_value(data, "is_active", True)),
        created_by=user_id,
        updated_by=user_id,
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def record_preventive_maintenance(
    db: Session,
    data: Any,
    current_user: Any | None = None,
) -> PreventiveMaintenanceRecord:
    user_id = _current_user_id(current_user)
    plan_id = _require_int(data, "plan_id")

    plan = _get_plan(db, plan_id)
    machine = _get_machine(db, plan.machine_id)

    status = _coerce_enum(_field_value(data, "status", PMRecordStatus.COMPLETED), PMRecordStatus, "status")
    scheduled_date = _field_value(data, "scheduled_date") or _today()
    performed_start_at = _field_value(data, "performed_start_at") or _utc_now()
    performed_end_at = _field_value(data, "performed_end_at")

    record = PreventiveMaintenanceRecord(
        plan_id=plan.id,
        machine_id=machine.id,
        scheduled_date=scheduled_date,
        performed_start_at=performed_start_at,
        performed_end_at=performed_end_at,
        status=status,
        findings=_field_value(data, "findings"),
        actions_taken=_field_value(data, "actions_taken"),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(record)

    # Rule: machine status changes while maintenance is being performed.
    if status == PMRecordStatus.COMPLETED:
        _set_machine_status(
            db,
            machine,
            MachineStatus.ACTIVE,
            "Preventive maintenance completed",
            user_id,
        )
        due_base = performed_end_at.date() if performed_end_at else scheduled_date
    else:
        _set_machine_status(
            db,
            machine,
            MachineStatus.UNDER_MAINTENANCE,
            "Preventive maintenance in progress",
            user_id,
        )
        due_base = scheduled_date

    # Rule: every PM record updates the plan next due date.
    plan.next_due_date = _next_due_by_frequency(due_base, plan.frequency_type, plan.frequency_days)
    plan.updated_by = user_id
    db.add(plan)

    db.commit()
    db.refresh(record)
    return record


def create_work_order(db: Session, data: Any, current_user: Any | None = None) -> MaintenanceWorkOrder:
    user_id = _current_user_id(current_user)
    machine_id = _require_int(data, "machine_id")
    breakdown_id = _require_int(data, "breakdown_id")

    machine = _get_machine(db, machine_id)
    breakdown = _get_breakdown(db, breakdown_id)

    if breakdown.machine_id != machine.id:
        raise MaintenanceBusinessRuleError("Breakdown does not belong to the selected machine")

    work_order = MaintenanceWorkOrder(
        work_order_number=str(_field_value(data, "work_order_number")),
        breakdown_id=breakdown.id,
        machine_id=machine.id,
        planned_start_at=_field_value(data, "planned_start_at"),
        actual_start_at=_field_value(data, "actual_start_at"),
        actual_end_at=_field_value(data, "actual_end_at"),
        root_cause=_field_value(data, "root_cause"),
        repair_action=_field_value(data, "repair_action"),
        status=_coerce_enum(_field_value(data, "status", WorkOrderStatus.CREATED), WorkOrderStatus, "status"),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(work_order)

    if breakdown.status == BreakdownStatus.OPEN:
        breakdown.status = BreakdownStatus.ASSIGNED
        breakdown.updated_by = user_id
        db.add(breakdown)

    _set_machine_status(db, machine, MachineStatus.UNDER_MAINTENANCE, "Maintenance work order created", user_id)

    db.commit()
    db.refresh(work_order)
    return work_order


def report_breakdown(db: Session, data: Any, current_user: Any | None = None) -> BreakdownReport:
    user_id = _current_user_id(current_user)
    machine_id = _require_int(data, "machine_id")
    machine = _get_machine(db, machine_id)

    breakdown = BreakdownReport(
        machine_id=machine.id,
        breakdown_number=str(_field_value(data, "breakdown_number")),
        reported_at=_field_value(data, "reported_at") or _utc_now(),
        symptom_description=str(_field_value(data, "symptom_description")),
        probable_cause=_field_value(data, "probable_cause"),
        severity=_coerce_enum(_field_value(data, "severity", BreakdownSeverity.MINOR), BreakdownSeverity, "severity"),
        status=_coerce_enum(_field_value(data, "status", BreakdownStatus.OPEN), BreakdownStatus, "status"),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(breakdown)
    db.flush()

    # Rule: every breakdown automatically generates a work order.
    wo_number = _field_value(data, "work_order_number") or f"WO-{breakdown.breakdown_number}"
    db.add(
        MaintenanceWorkOrder(
            work_order_number=str(wo_number),
            breakdown_id=breakdown.id,
            machine_id=machine.id,
            planned_start_at=_field_value(data, "planned_start_at"),
            actual_start_at=None,
            actual_end_at=None,
            status=WorkOrderStatus.CREATED,
            created_by=user_id,
            updated_by=user_id,
        )
    )

    breakdown.status = BreakdownStatus.ASSIGNED
    breakdown.updated_by = user_id
    db.add(breakdown)

    _set_machine_status(db, machine, MachineStatus.UNDER_MAINTENANCE, "Breakdown reported", user_id)

    db.commit()
    db.refresh(breakdown)
    return breakdown


def complete_work_order(
    db: Session,
    work_order_id: int,
    data: Any | None = None,
    current_user: Any | None = None,
) -> MaintenanceWorkOrder:
    payload = data or {}
    user_id = _current_user_id(current_user)

    work_order = _get_work_order(db, work_order_id)
    breakdown = _get_breakdown(db, work_order.breakdown_id)
    machine = _get_machine(db, work_order.machine_id)

    work_order.status = WorkOrderStatus.COMPLETED
    work_order.actual_start_at = _field_value(payload, "actual_start_at", work_order.actual_start_at or _utc_now())
    work_order.actual_end_at = _field_value(payload, "actual_end_at", _utc_now())
    work_order.root_cause = _field_value(payload, "root_cause", work_order.root_cause)
    work_order.repair_action = _field_value(payload, "repair_action", work_order.repair_action)
    work_order.updated_by = user_id
    db.add(work_order)

    breakdown.status = _coerce_enum(
        _field_value(payload, "breakdown_status", BreakdownStatus.RESOLVED),
        BreakdownStatus,
        "breakdown_status",
    )
    breakdown.updated_by = user_id
    db.add(breakdown)

    _set_machine_status(db, machine, MachineStatus.ACTIVE, "Maintenance work order completed", user_id)

    db.commit()
    db.refresh(work_order)
    return work_order


def record_machine_downtime(db: Session, data: Any, current_user: Any | None = None) -> MachineDowntime:
    user_id = _current_user_id(current_user)
    machine_id = _require_int(data, "machine_id")
    _get_machine(db, machine_id)

    start_at = _field_value(data, "downtime_start_at")
    end_at = _field_value(data, "downtime_end_at")
    duration_minutes = _field_value(data, "duration_minutes")

    if duration_minutes is None and start_at and end_at:
        delta = end_at - start_at
        duration_minutes = max(int(delta.total_seconds() // 60), 0)

    downtime = MachineDowntime(
        machine_id=machine_id,
        source_type=_coerce_enum(
            _field_value(data, "source_type", DowntimeSourceType.OTHER),
            DowntimeSourceType,
            "source_type",
        ),
        source_id=_field_value(data, "source_id"),
        downtime_start_at=start_at,
        downtime_end_at=end_at,
        duration_minutes=duration_minutes,
        is_planned=bool(_field_value(data, "is_planned", False)),
        reason_code=_field_value(data, "reason_code"),
        remarks=_field_value(data, "remarks"),
        created_by=user_id,
        updated_by=user_id,
    )

    db.add(downtime)
    db.commit()
    db.refresh(downtime)
    return downtime


def get_machine_history(db: Session, machine_id: int) -> dict[str, Any]:
    _get_machine(db, machine_id)

    histories = db.scalars(
        select(MachineHistory)
        .where(
            MachineHistory.machine_id == machine_id,
            MachineHistory.is_deleted.is_(False),
        )
        .order_by(MachineHistory.event_datetime.desc())
    ).all()

    pm_records = db.scalars(
        select(PreventiveMaintenanceRecord)
        .where(
            PreventiveMaintenanceRecord.machine_id == machine_id,
            PreventiveMaintenanceRecord.is_deleted.is_(False),
        )
        .order_by(PreventiveMaintenanceRecord.scheduled_date.desc())
    ).all()

    breakdowns = db.scalars(
        select(BreakdownReport)
        .where(
            BreakdownReport.machine_id == machine_id,
            BreakdownReport.is_deleted.is_(False),
        )
        .order_by(BreakdownReport.reported_at.desc())
    ).all()

    work_orders = db.scalars(
        select(MaintenanceWorkOrder)
        .where(
            MaintenanceWorkOrder.machine_id == machine_id,
            MaintenanceWorkOrder.is_deleted.is_(False),
        )
        .order_by(MaintenanceWorkOrder.id.desc())
    ).all()

    downtimes = db.scalars(
        select(MachineDowntime)
        .where(
            MachineDowntime.machine_id == machine_id,
            MachineDowntime.is_deleted.is_(False),
        )
        .order_by(MachineDowntime.downtime_start_at.desc())
    ).all()

    return {
        "machine_id": machine_id,
        "history": histories,
        "preventive_maintenance_records": pm_records,
        "breakdowns": breakdowns,
        "work_orders": work_orders,
        "downtimes": downtimes,
    }
