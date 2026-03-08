# AS9100D ERP Backend

FastAPI backend for an AS9100D-oriented manufacturing ERP. The current implementation covers auth/RBAC, users/roles administration, sales, purchase, engineering, stores, production, quality, maintenance, dispatch, and admin dashboards.

## Current Modules
- Auth: login, refresh rotation, logout, sessions, password change, forgot/reset password, Google OAuth.
- Users and Roles: admin-managed user lifecycle, role maintenance, and multi-module access assignment.
- Sales: enquiry, contract review, quotation, customer PO review, sales order.
- Purchase: supplier approval, purchase order lifecycle, PDF download.
- Engineering: drawing revision control and route card release.
- Stores: GRN, MTC, RMIR, inventory posting, issue, storage locations.
- Production: production order, operation execution, operator assignment, in-process inspection, rework, production logging, FAI trigger, and production reports.
- Quality: incoming/in-process/final inspections, FAI, NCR/CAPA, root cause analysis, gauges, audit records, batch traceability, and PDF reports.
- Maintenance: machine master lifecycle, preventive maintenance plans, breakdown reporting, corrective work orders, downtime tracking, and machine history traceability.
- Dispatch: dispatch order lifecycle, dispatch checklist verification, packing list/invoice/challan creation, shipment release gating, and dispatch PDF downloads.
- Admin: global search, audit log viewer, dashboard summary, analytics endpoints, and configurable dashboard alerts.

## Access Control Model
- `Admin` manages users, roles, and role-module assignments.
- Business module APIs are protected by `require_roles(...)` and `role_module_access`.
- Default business roles map to their own module, for example `Sales -> sales`, `Production -> production`, `Stores -> stores`.
- Admin can explicitly grant multiple business modules to a role through `PUT /api/v1/roles/{role_id}/modules`.
- Inactive users, locked users, soft-deleted users, and users attached to inactive roles are blocked from protected APIs.
- `POST /api/v1/users/` is admin-only. There is no public user-registration endpoint.

## Production Highlights
- Production orders require a released route card.
- Operation start is sequence-controlled and blocked until prior operations are completed.
- Operation start and production logging are blocked when the linked machine is inactive.
- Operation start is also blocked when the maintenance-tracked machine has status `UnderMaintenance`.
- Operation completion requires the latest in-process inspection result to be `Pass`.
- Failed inspection auto-creates a rework order.
- Rework order closure requires a later passed inspection.
- Production order completion requires:
  - all operations completed
  - no open rework orders
  - `produced_quantity + scrap_quantity == planned_quantity`
- Batch, operator, machine, and job progress reports are available under `/api/v1/production/report/*`.

## Setup
1. Create and activate a virtual environment.
2. Install dependencies.
3. Configure `.env` with the PostgreSQL connection string and auth settings.
4. Run migrations:

```powershell
alembic upgrade head
```

5. Start the API:

```powershell
.\scripts\start-api-dev.ps1
```

This script scopes auto-reload to `app/` and `alembic/` so test runs, docs edits, and generated files do not trigger noisy reload cycles during development.

If you want a one-off foreground process without reload:

```powershell
.\scripts\start-api-dev.ps1 -NoReload
```

## Testing
- Full suite:

```powershell
pytest -q
```

- Fast run excluding slow tests:

```powershell
pytest -m "not slow" -q
```

## Docs
- ERD index: [docs/er-diagrams/index.md](docs/er-diagrams/index.md)
- Auth & RBAC ERD: [docs/er-diagrams/auth-rbac-erd.md](docs/er-diagrams/auth-rbac-erd.md)
- Admin ERD: [docs/er-diagrams/admin-erd.md](docs/er-diagrams/admin-erd.md)
- Dispatch ERD: [docs/er-diagrams/dispatch-erd.md](docs/er-diagrams/dispatch-erd.md)
- Engineering ERD: [docs/er-diagrams/engineering-erd.md](docs/er-diagrams/engineering-erd.md)
- Production ERD: [docs/er-diagrams/production-erd.md](docs/er-diagrams/production-erd.md)
- Quality ERD: [docs/er-diagrams/quality-erd.md](docs/er-diagrams/quality-erd.md)
- Maintenance ERD: [docs/er-diagrams/maintenance-erd.md](docs/er-diagrams/maintenance-erd.md)
- Auth SOP: [docs/sop/auth-operations-sop.md](docs/sop/auth-operations-sop.md)
- Admin SOP: [docs/sop/admin-operations-sop.md](docs/sop/admin-operations-sop.md)
- Dispatch SOP: [docs/sop/dispatch-operations-sop.md](docs/sop/dispatch-operations-sop.md)
- Engineering SOP: [docs/sop/engineering-operations-sop.md](docs/sop/engineering-operations-sop.md)
- Production SOP: [docs/sop/production-operations-sop.md](docs/sop/production-operations-sop.md)
- Stores SOP: [docs/sop/stores-operations-sop.md](docs/sop/stores-operations-sop.md)
- Quality SOP: [docs/sop/quality-operations-sop.md](docs/sop/quality-operations-sop.md)
- Maintenance SOP: [docs/sop/maintenance-operations-sop.md](docs/sop/maintenance-operations-sop.md)

## Postman Collections
- Auth lifecycle: [docs/postman/AS9100D-Auth-Lifecycle.postman_collection.json](docs/postman/AS9100D-Auth-Lifecycle.postman_collection.json)
- Users & Roles admin: [docs/postman/AS9100D-Users-Roles-Admin.postman_collection.json](docs/postman/AS9100D-Users-Roles-Admin.postman_collection.json)
- Admin dashboards: [docs/postman/AS9100D-Admin-Dashboard.postman_collection.json](docs/postman/AS9100D-Admin-Dashboard.postman_collection.json)
- Dispatch lifecycle: [docs/postman/AS9100D-Dispatch-Lifecycle.postman_collection.json](docs/postman/AS9100D-Dispatch-Lifecycle.postman_collection.json)
- Sales lifecycle: [docs/postman/AS9100D-Sales-Lifecycle.postman_collection.json](docs/postman/AS9100D-Sales-Lifecycle.postman_collection.json)
- Purchase lifecycle: [docs/postman/AS9100D-Purchase-Lifecycle.postman_collection.json](docs/postman/AS9100D-Purchase-Lifecycle.postman_collection.json)
- Engineering lifecycle: [docs/postman/AS9100D-Engineering-RouteCard-Lifecycle.postman_collection.json](docs/postman/AS9100D-Engineering-RouteCard-Lifecycle.postman_collection.json)
- Stores lifecycle: [docs/postman/AS9100D-Stores-Lifecycle.postman_collection.json](docs/postman/AS9100D-Stores-Lifecycle.postman_collection.json)
- Production lifecycle: [docs/postman/AS9100D-Production-Lifecycle.postman_collection.json](docs/postman/AS9100D-Production-Lifecycle.postman_collection.json)
- Quality lifecycle: [docs/postman/AS9100D-Quality-Lifecycle.postman_collection.json](docs/postman/AS9100D-Quality-Lifecycle.postman_collection.json)
- Maintenance lifecycle: [docs/postman/AS9100D-Maintenance-Lifecycle.postman_collection.json](docs/postman/AS9100D-Maintenance-Lifecycle.postman_collection.json)
- Postman usage guide: [docs/postman/README.md](docs/postman/README.md)
