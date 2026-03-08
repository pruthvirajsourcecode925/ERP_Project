# Maintenance Operations SOP (Backend API)

## Purpose
Defines standard Maintenance workflows for machine lifecycle management, preventive maintenance scheduling, breakdown reporting, corrective work orders, downtime tracking, and machine history traceability.

## Preconditions
- Authenticated user with `Maintenance` or `Admin` access for write operations.
- Read-only endpoints also allow `Production` role access.
- Up-to-date schema (`alembic upgrade head`) so Maintenance tables exist.

## Machine Master Management
1. Create a maintenance-tracked machine: `POST /api/v1/maintenance/machine`
   - Required fields: `machine_code`, `machine_name`, `work_center`.
   - Default status: `Active`.
   - Auto-creates an `Installed` history record.
2. List all machines: `GET /api/v1/maintenance/machine`

## Preventive Maintenance (PM) Flow
1. Create a PM plan for a machine: `POST /api/v1/maintenance/preventive-plan`
   - Required: `machine_id`, `plan_code`, `frequency_type`.
   - Supports frequency types: Daily, Weekly, Monthly, Quarterly, HalfYearly, Annual, RuntimeBased.
   - Optional: `checklist_template`, `standard_reference`, `next_due_date`.
2. List all PM plans: `GET /api/v1/maintenance/preventive-plan`

## Breakdown Reporting Flow
1. Report a machine breakdown: `POST /api/v1/maintenance/breakdown`
   - Required: `machine_id`, `breakdown_number`, `reported_at`, `symptom_description`, `severity`.
   - Severity levels: Minor, Major, Critical.
   - Service automatically sets machine status to `UnderMaintenance`.
   - Auto-creates status-change history record.
   - For `Critical` severity, an auto-generated work order is created.

## Corrective Work Order Flow
1. Create a work order for a breakdown: `POST /api/v1/maintenance/work-order`
   - Required: `work_order_number`, `breakdown_id`, `machine_id`.
   - Initial status: `Created`.
2. Complete a work order: `PATCH /api/v1/maintenance/work-order/{id}/complete`
   - Sets status to `Completed`, records actual times, root cause, and repair action.
   - Optionally updates the breakdown report status.
   - If breakdown status set to `Resolved` or `Closed`, machine status is restored to `Active`.

## Downtime Tracking
1. Record machine downtime: `POST /api/v1/maintenance/downtime`
   - Required: `machine_id`, `source_type`, `downtime_start_at`.
   - Source types: Breakdown, PreventiveMaintenance, Setup, Utilities, Other.
   - Use `is_planned` flag to distinguish planned PM downtime from unplanned breakdowns.

## Machine History and Traceability
1. Get full machine history: `GET /api/v1/maintenance/history/{machine_id}`
   - Returns combined view of:
     - Machine event history (installations, relocations, calibration, status changes)
     - Preventive maintenance records
     - Breakdown reports
     - Work orders
     - Downtime records

## Control Rules
- Machine status values: `Active`, `Inactive`, `UnderMaintenance`, `Decommissioned`.
- Breakdown reporting with `Critical` severity auto-generates a work order.
- Breakdown reporting auto-transitions machine status to `UnderMaintenance`.
- Work order completion with breakdown resolved/closed restores machine to `Active`.
- Machine status `UnderMaintenance` blocks production operation start (cross-module validation).
- Write endpoints require `Maintenance` or `Admin` role.
- Read endpoints additionally allow `Production` role.
- All records support soft-delete via `is_deleted` flag.

## Validation Checklist
- Create machine -> verify `Installed` history record auto-created.
- Report breakdown -> verify machine status changed to `UnderMaintenance`.
- Report `Critical` breakdown -> verify auto-generated work order.
- Complete work order with breakdown `Resolved` -> verify machine status restored to `Active`.
- Attempt production operation start on `UnderMaintenance` machine -> must fail.
- `Production` role user -> can read machines and history but cannot create/modify records.
- `GET /api/v1/maintenance/machine` returns `200` with machine list.
- `GET /api/v1/maintenance/history/{machine_id}` returns combined traceability data.

## Operational Notes
- Machine codes must be unique across the maintenance module.
- PM plan codes must be unique.
- Breakdown numbers and work order numbers must be unique.
- All timestamps use UTC with timezone awareness.
- Downtime `source_id` is a polymorphic reference — not enforced by FK constraint.
