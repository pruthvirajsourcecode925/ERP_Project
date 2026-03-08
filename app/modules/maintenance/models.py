from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class MachineStatus(str, PyEnum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    UNDER_MAINTENANCE = "UnderMaintenance"
    DECOMMISSIONED = "Decommissioned"


class MachineHistoryEventType(str, PyEnum):
    INSTALLED = "Installed"
    RELOCATED = "Relocated"
    UPGRADED = "Upgraded"
    CALIBRATION = "Calibration"
    STATUS_CHANGE = "StatusChange"
    RETIRED = "Retired"
    OTHER = "Other"


class MaintenanceFrequencyType(str, PyEnum):
    DAILY = "Daily"
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"
    HALF_YEARLY = "HalfYearly"
    ANNUAL = "Annual"
    RUNTIME_BASED = "RuntimeBased"


class PMRecordStatus(str, PyEnum):
    PLANNED = "Planned"
    COMPLETED = "Completed"
    DEFERRED = "Deferred"
    MISSED = "Missed"
    PARTIAL = "PartiallyCompleted"


class BreakdownSeverity(str, PyEnum):
    MINOR = "Minor"
    MAJOR = "Major"
    CRITICAL = "Critical"


class BreakdownStatus(str, PyEnum):
    OPEN = "Open"
    UNDER_INVESTIGATION = "UnderInvestigation"
    ASSIGNED = "Assigned"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class WorkOrderStatus(str, PyEnum):
    CREATED = "Created"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    VERIFIED = "Verified"
    CANCELLED = "Cancelled"


class DowntimeSourceType(str, PyEnum):
    BREAKDOWN = "Breakdown"
    PREVENTIVE_MAINTENANCE = "PreventiveMaintenance"
    SETUP = "Setup"
    UTILITIES = "Utilities"
    OTHER = "Other"


class MaintenanceAuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class MaintenanceMachine(Base, MaintenanceAuditMixin):
    __tablename__ = "maintenance_machines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    machine_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    machine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    commissioned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MachineStatus] = mapped_column(
        Enum(MachineStatus, name="maintenance_machine_status", values_callable=enum_values),
        default=MachineStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    histories: Mapped[list["MachineHistory"]] = relationship(back_populates="machine", cascade="all, delete-orphan")
    preventive_maintenance_plans: Mapped[list["PreventiveMaintenancePlan"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan"
    )
    breakdown_reports: Mapped[list["BreakdownReport"]] = relationship(back_populates="machine", cascade="all, delete-orphan")
    downtimes: Mapped[list["MachineDowntime"]] = relationship(back_populates="machine", cascade="all, delete-orphan")


class MachineHistory(Base, MaintenanceAuditMixin):
    __tablename__ = "machine_histories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[MachineHistoryEventType] = mapped_column(
        Enum(MachineHistoryEventType, name="machine_history_event_type", values_callable=enum_values),
        nullable=False,
        index=True,
    )
    event_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    machine: Mapped["MaintenanceMachine"] = relationship("MaintenanceMachine", back_populates="histories")


class PreventiveMaintenancePlan(Base, MaintenanceAuditMixin):
    __tablename__ = "preventive_maintenance_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    frequency_type: Mapped[MaintenanceFrequencyType] = mapped_column(
        Enum(MaintenanceFrequencyType, name="pm_frequency_type", values_callable=enum_values),
        nullable=False,
        index=True,
    )
    frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checklist_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    machine: Mapped["MaintenanceMachine"] = relationship(
        "MaintenanceMachine", back_populates="preventive_maintenance_plans"
    )
    records: Mapped[list[PreventiveMaintenanceRecord]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PreventiveMaintenanceRecord(Base, MaintenanceAuditMixin):
    __tablename__ = "preventive_maintenance_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("preventive_maintenance_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    performed_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    performed_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[PMRecordStatus] = mapped_column(
        Enum(PMRecordStatus, name="pm_record_status", values_callable=enum_values),
        default=PMRecordStatus.PLANNED,
        nullable=False,
        index=True,
    )
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions_taken: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[PreventiveMaintenancePlan] = relationship(back_populates="records")
    machine: Mapped["MaintenanceMachine"] = relationship("MaintenanceMachine")


class BreakdownReport(Base, MaintenanceAuditMixin):
    __tablename__ = "breakdown_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    breakdown_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    symptom_description: Mapped[str] = mapped_column(Text, nullable=False)
    probable_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[BreakdownSeverity] = mapped_column(
        Enum(BreakdownSeverity, name="breakdown_severity", values_callable=enum_values),
        nullable=False,
        index=True,
    )
    status: Mapped[BreakdownStatus] = mapped_column(
        Enum(BreakdownStatus, name="breakdown_status", values_callable=enum_values),
        default=BreakdownStatus.OPEN,
        nullable=False,
        index=True,
    )

    machine: Mapped["MaintenanceMachine"] = relationship("MaintenanceMachine", back_populates="breakdown_reports")
    work_orders: Mapped[list[MaintenanceWorkOrder]] = relationship(
        back_populates="breakdown_report", cascade="all, delete-orphan"
    )


class MaintenanceWorkOrder(Base, MaintenanceAuditMixin):
    __tablename__ = "maintenance_work_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    work_order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    breakdown_id: Mapped[int] = mapped_column(
        ForeignKey("breakdown_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus, name="maintenance_work_order_status", values_callable=enum_values),
        default=WorkOrderStatus.CREATED,
        nullable=False,
        index=True,
    )

    breakdown_report: Mapped[BreakdownReport] = relationship(back_populates="work_orders")
    machine: Mapped["MaintenanceMachine"] = relationship("MaintenanceMachine")


class MachineDowntime(Base, MaintenanceAuditMixin):
    __tablename__ = "machine_downtimes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[DowntimeSourceType] = mapped_column(
        Enum(DowntimeSourceType, name="machine_downtime_source_type", values_callable=enum_values),
        nullable=False,
        index=True,
    )
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    downtime_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    downtime_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_planned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    machine: Mapped["MaintenanceMachine"] = relationship("MaintenanceMachine", back_populates="downtimes")
