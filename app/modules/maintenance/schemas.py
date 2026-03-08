from __future__ import annotations

from datetime import date, datetime

try:
    from pydantic import BaseModel, ConfigDict
except ImportError:
    from pydantic import BaseModel
    ConfigDict = None

from app.modules.maintenance.models import (
    BreakdownSeverity,
    BreakdownStatus,
    DowntimeSourceType,
    MachineStatus,
    MaintenanceFrequencyType,
    WorkOrderStatus,
)


class ORMResponseModel(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True


class MachineCreate(BaseModel):
    machine_code: str
    machine_name: str
    work_center: str
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    commissioned_date: date | None = None
    status: MachineStatus = MachineStatus.ACTIVE


class MachineResponse(ORMResponseModel):
    id: int
    machine_code: str
    machine_name: str
    work_center: str
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    commissioned_date: date | None = None
    status: MachineStatus


class PreventiveMaintenancePlanCreate(BaseModel):
    machine_id: int
    plan_code: str
    frequency_type: MaintenanceFrequencyType
    frequency_days: int | None = None
    runtime_interval_hours: int | None = None
    checklist_template: str | None = None
    standard_reference: str | None = None
    next_due_date: date | None = None
    is_active: bool = True


class PreventiveMaintenancePlanResponse(ORMResponseModel):
    id: int
    machine_id: int
    plan_code: str
    frequency_type: MaintenanceFrequencyType
    frequency_days: int | None = None
    runtime_interval_hours: int | None = None
    checklist_template: str | None = None
    standard_reference: str | None = None
    next_due_date: date | None = None
    is_active: bool


class BreakdownReportCreate(BaseModel):
    machine_id: int
    breakdown_number: str
    reported_at: datetime
    symptom_description: str
    probable_cause: str | None = None
    severity: BreakdownSeverity
    status: BreakdownStatus = BreakdownStatus.OPEN


class BreakdownReportResponse(ORMResponseModel):
    id: int
    machine_id: int
    breakdown_number: str
    reported_at: datetime
    symptom_description: str
    probable_cause: str | None = None
    severity: BreakdownSeverity
    status: BreakdownStatus


class MaintenanceWorkOrderCreate(BaseModel):
    work_order_number: str
    breakdown_id: int
    machine_id: int
    planned_start_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    root_cause: str | None = None
    repair_action: str | None = None
    status: WorkOrderStatus = WorkOrderStatus.CREATED


class MaintenanceWorkOrderResponse(ORMResponseModel):
    id: int
    work_order_number: str
    breakdown_id: int
    machine_id: int
    planned_start_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    root_cause: str | None = None
    repair_action: str | None = None
    status: WorkOrderStatus


class MachineDowntimeCreate(BaseModel):
    machine_id: int
    source_type: DowntimeSourceType
    source_id: int | None = None
    downtime_start_at: datetime
    downtime_end_at: datetime | None = None
    duration_minutes: int | None = None
    is_planned: bool = False
    reason_code: str | None = None
    remarks: str | None = None


class MachineDowntimeResponse(ORMResponseModel):
    id: int
    machine_id: int
    source_type: DowntimeSourceType
    source_id: int | None = None
    downtime_start_at: datetime
    downtime_end_at: datetime | None = None
    duration_minutes: int | None = None
    is_planned: bool
    reason_code: str | None = None
    remarks: str | None = None
