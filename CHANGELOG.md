# Changelog

## 2026-03-08 — Dispatch Module and Admin Dashboard Readiness

### Added
- Dispatch module API under `/api/v1/dispatch/*`:
  - Dispatch order creation and listing.
  - Dispatch item and checklist management.
  - Packing list, invoice, and delivery challan generation.
  - Invoice and challan PDF download endpoints.
  - Completion gate enforcing checklist approval, CoC linkage, shipping documents, and passed final inspection.
- Dispatch ORM models, schemas, services, report generators, and router registration.
- Admin dashboard extensions:
  - Global search endpoint.
  - Audit log viewer endpoint.
  - Dashboard summary endpoint.
  - Analytics endpoints for production trend, quality distribution, dispatch trend, supplier performance, machine utilization, and user performance.
  - Configurable alert settings and dashboard alerts endpoints.
- Alert settings schema migration:
  - `alembic/versions/20260308_0017_add_alert_settings.py`.
- Test coverage for:
  - security access controls
  - dispatch lifecycle, business rules, RBAC, and PDF generation
  - alerts and admin APIs
  - PDF validation
  - maintenance cross-module validation
  - API performance and broader end-to-end flows

### Changed
- `README.md` now documents dispatch and admin capabilities plus related docs and Postman assets.
- ERD and SOP documentation set expanded to cover dispatch and admin/governance flows.
- Postman guide updated with dispatch and admin collections.
- Alembic environment imports now include admin alert settings metadata.

### Fixed
- Repository hygiene for release: generated dispatch PDFs are no longer intended for version control and are ignored through `.gitignore`.

### Documentation
- Added `docs/er-diagrams/admin-erd.md`.
- Added `docs/er-diagrams/dispatch-erd.md`.
- Added `docs/sop/admin-operations-sop.md`.
- Added `docs/sop/dispatch-operations-sop.md`.
- Added `docs/postman/AS9100D-Admin-Dashboard.postman_collection.json`.
- Added `docs/postman/AS9100D-Dispatch-Lifecycle.postman_collection.json`.
- Updated `docs/er-diagrams/index.md`.
- Updated `docs/postman/README.md`.

## 2026-03-08 — Maintenance Module & Production Integration

### Added
- **Maintenance module** with full API endpoints (`/api/v1/maintenance/*`):
  - Machine master management: `POST/GET /maintenance/machine`.
  - Preventive maintenance plans: `POST/GET /maintenance/preventive-plan`.
  - Breakdown reporting: `POST /maintenance/breakdown` with auto status transition and auto work-order for critical severity.
  - Corrective work orders: `POST /maintenance/work-order`, `PATCH /maintenance/work-order/{id}/complete`.
  - Downtime tracking: `POST /maintenance/downtime`.
  - Machine history traceability: `GET /maintenance/history/{machine_id}`.
- Maintenance ORM models: `MaintenanceMachine`, `MachineHistory`, `PreventiveMaintenancePlan`, `PreventiveMaintenanceRecord`, `BreakdownReport`, `MaintenanceWorkOrder`, `MachineDowntime`.
- Maintenance schemas, services, and routers under `app/modules/maintenance/`.
- Production-maintenance integration: `validate_machine_available()` blocks operation start when machine is `UnderMaintenance`.
- Comprehensive test suite: `tests/test_maintenance.py` (10 test functions covering CRUD, status transitions, cross-module validation, role-based access, and traceability).

### Changed
- Renamed maintenance `Machine` class to `MaintenanceMachine` to resolve SQLAlchemy mapper conflict with production `Machine` class.
- Production service uses raw SQL check against `maintenance_machines` table to avoid cross-module ORM import conflicts.
- Simplified production model relationship strings after eliminating class name collision.

### Fixed
- SQLAlchemy `InvalidRequestError: Multiple classes found for path "Machine"` — resolved by disambiguating class names.
- Removed invalid cross-module `production_operations` relationship from maintenance model (FK pointed to wrong table).
- Resolved merge conflict in `ERD-DIAGRAMS.md`.

### Documentation
- Added `docs/er-diagrams/maintenance-erd.md` with full Mermaid ER diagram.
- Added `docs/sop/maintenance-operations-sop.md`.
- Added `docs/postman/AS9100D-Maintenance-Lifecycle.postman_collection.json`.
- Updated `docs/er-diagrams/index.md` with Maintenance ERD link.
- Updated `docs/postman/README.md` with Maintenance collection in import order.
- Updated `docs/sop/production-operations-sop.md` with maintenance gate precondition and validation check.
- Updated `README.md` with Maintenance module description, endpoints, and doc links.
- Updated `ERD-DIAGRAMS.md` — resolved merge conflict, added Quality and Maintenance links.

## 2026-03-08 — Quality, Reporting, and Documentation Alignment

### Added
- Quality module extensions:
  - `NCR.defect_category` support.
  - New entities: `InspectionMeasurement`, `CertificateOfConformance`, `QualityMetric`.
- Quality traceability and reporting:
  - Batch/NCR/customer traceability APIs.
  - PDF report generation and download endpoints for FIR, FAI, NCR, CAPA, Audit, and Batch Traceability.
  - Auto-creation of report directories under `storage/quality_reports/*`.
- Database migration for new Quality schema artifacts:
  - `alembic/versions/20260308_0015_add_quality_extensions.py`.

### Changed
- Production report date filtering now uses explicit UTC day-boundary windows for stable aggregation behavior across environments.
- Development startup guidance now uses scoped reload script: `scripts/start-api-dev.ps1`.

### Fixed
- Quality model mapping issue in root-cause relationship foreign key configuration.
- Production/Stores behavior regressions found during full-suite validation.
- Runtime schema mismatch for Quality (`ncrs.defect_category`) addressed via migration.

### Validation
- Full test suite status: `144 passed`.
- Quality smoke checks (`/quality/ncr`, `/quality/capa`, `/quality/gauge`) return `200`.

### Documentation
- Added `docs/er-diagrams/quality-erd.md`.
- Added `docs/sop/quality-operations-sop.md`.
- Updated Production and Engineering SOP/ERD docs for endpoint/schema accuracy.
- Added and updated Postman collections including:
  - `docs/postman/AS9100D-Quality-Lifecycle.postman_collection.json`
  - `docs/postman/AS9100D-Production-Lifecycle.postman_collection.json`
  - `docs/postman/README.md`

## 2026-03-01 — Phase-1 Validation & Hardening

### Added
- User management enhancements:
  - Admin user list filters (`username`, `role`, `is_locked`, `auth_provider`) with pagination support.
  - Admin actions: unlock user, disable user, enable user.
  - Soft-delete endpoint support for users.
- Test coverage for new user filters and admin user-state endpoints.

### Changed
- Role read endpoints (`list`, `get`) now require admin authorization for strict role CRUD governance.
- Configuration defaults hardened to avoid sensitive hardcoded values in source.

### Security
- Secrets and environment-specific credentials are expected from `.env`; `.env.example` remains the template.
- Existing auth capabilities retained and validated: JWT access/refresh, local+Google auth support, account lockout controls, password reset flow.

### Validation
- Full test suite status after validation/fixes: `34 passed`.

### Notes
- This release finalizes Phase-1 backend validation and stabilization.
- Phase-2 work has not started in this release.
