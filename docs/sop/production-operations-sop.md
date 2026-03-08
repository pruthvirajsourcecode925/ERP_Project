# Production Operations SOP

## Purpose
Defines the backend operating flow for production execution, inspection, rework control, output logging, and production reporting.

## Preconditions
- Authenticated user with `Production` or `Admin` access.
- Sales order and route card already exist.
- Route card must be `Released`.
- Production operations are expected to exist before operation execution starts.
- If an operation is machine-linked, the machine must be active.
- If the machine is tracked in the maintenance module and has status `UnderMaintenance`, operation start is blocked.

## Standard Flow
1. Create machine master if required with `POST /api/v1/production/machine`.
2. Create production order with `POST /api/v1/production/order`.
3. Release production order with `PATCH /api/v1/production/order/{id}/release`.
4. Start production order with `PATCH /api/v1/production/order/{id}/start`.
5. Start operation with `POST /api/v1/production/operation/{id}/start`.
6. Assign one or more production operators with `POST /api/v1/production/operation/{id}/assign-operator`.
7. Record in-process inspection with `POST /api/v1/production/operation/{id}/inspection`.
8. If inspection fails, rework is auto-created. Rework can also be created manually with `POST /api/v1/production/rework`.
9. After corrective action and a later passed inspection, close rework with `PATCH /api/v1/production/rework/{id}/close`.
10. Complete the operation with `POST /api/v1/production/operation/{id}/complete`.
11. Record production output with `POST /api/v1/production/log`.
12. Review reports:
   - `GET /api/v1/production/report/batch`
   - `GET /api/v1/production/report/operator`
   - `GET /api/v1/production/report/machine`
   - `GET /api/v1/production/report/job`
13. Complete the production order with `PATCH /api/v1/production/order/{id}/complete`.

## Control Rules
- Production order creation and start are blocked unless the linked route card is released.
- Operation start is sequence-controlled: a later operation cannot start before all lower operation numbers are completed.
- Operation start and production logging are blocked when the linked machine is inactive.
- Operator assignment accepts multiple operators, but assigned operators must exist and hold the `Production` role.
- Operation completion is blocked unless the latest in-process inspection result is `Pass`.
- Failed in-process inspection auto-creates a rework order in `Open` status.
- Rework closure is blocked unless the latest inspection for that operation is `Pass`.
- Production log totals cannot exceed planned quantity.
- Production order completion is blocked unless:
  - all operations are completed
  - all rework orders are closed
  - `produced_quantity + scrap_quantity == planned_quantity`
- First-operation completion can auto-create an FAI trigger.

## Validation Checklist
- Route card not released -> production order create/start must fail.
- Starting operation 20 before operation 10 completion must fail.
- Inactive machine linked to an operation must block operation start.
- Machine with maintenance status `UnderMaintenance` must block operation start.
- Inactive machine in production log must block production output logging.
- Failed inspection must create exactly one open rework order.
- Rework close attempt before a later passed inspection must fail.
- Production order completion with unreconciled quantity must fail.
- Batch, operator, machine, and job reports must return read-only aggregated data.

## Reporting Notes
- Batch report aggregates production log records by `batch_number` and date range.
- Operator report aggregates jobs worked, completed operations, production quantity, and scrap.
- Machine report aggregates operations, production quantity, scrap quantity, and operators used.
- Job report shows planned quantity, produced quantity, scrap quantity, remaining quantity, and operation status counts.
- Date filters for batch/operator/machine reports are interpreted as full-day boundaries in UTC: `start_date 00:00:00` (inclusive) to `end_date + 1 day 00:00:00` (exclusive).

## Traceability
- Production logs carry batch, operator, machine, and timestamp traceability fields.
- In-process inspection and rework records preserve corrective-action history.
- FAI trigger records preserve first-operation verification requirements.
