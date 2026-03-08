# Quality Operations SOP (Backend API)

## Purpose
Defines standard Quality workflows for inspections, NCR/CAPA control, audit records, traceability, and downloadable reports.

## Preconditions
- Authenticated user with `Quality` or `Admin` access.
- Up-to-date schema (`alembic upgrade head`) so Quality extension columns/tables exist.
- Upstream records exist as required:
  - GRN/GRN Item for incoming inspection
  - Production operation/order for in-process/final inspection and FAI
  - Gauge master for gauge-linked measurements

## Core Inspection Flow
1. Complete incoming inspection: `PATCH /api/v1/quality/incoming-inspection/{id}/result`
2. Complete in-process inspection: `PATCH /api/v1/quality/inprocess-inspection/{id}/complete`
3. Complete final inspection: `PATCH /api/v1/quality/final-inspection/{id}/complete`
4. Create FAI report when required: `POST /api/v1/quality/fai`
5. Retrieve FAI: `GET /api/v1/quality/fai/{id}`

## Nonconformance and Corrective Action
1. Create NCR: `POST /api/v1/quality/ncr`
2. List NCRs: `GET /api/v1/quality/ncr`
3. Add root-cause analysis: `POST /api/v1/quality/root-cause`
4. Create CAPA: `POST /api/v1/quality/capa`
5. List CAPA: `GET /api/v1/quality/capa`
6. Close NCR after corrective actions: `PATCH /api/v1/quality/ncr/{id}/close`

## Gauge and Audit Controls
1. Create gauge master: `POST /api/v1/quality/gauge`
2. List gauges: `GET /api/v1/quality/gauge`
3. Create audit plan: `POST /api/v1/quality/audit-plan`
4. Create audit report: `POST /api/v1/quality/audit-report`
5. Record management review meeting: `POST /api/v1/quality/mrm`

## Traceability Workflows
1. Batch genealogy view: `GET /api/v1/quality/trace/batch/{batch_number}`
2. NCR impact view: `GET /api/v1/quality/trace/ncr/{ncr_id}`
3. Customer trace view: `GET /api/v1/quality/trace/customer/{customer_id}`

## Downloadable Reports
- FIR: `GET /api/v1/quality/report/fir/{inspection_id}`
- FAI: `GET /api/v1/quality/report/fai/{fai_id}`
- NCR: `GET /api/v1/quality/report/ncr/{ncr_id}`
- CAPA: `GET /api/v1/quality/report/capa/{capa_id}`
- Audit: `GET /api/v1/quality/report/audit/{audit_id}`
- Batch traceability: `GET /api/v1/quality/report/trace/{batch_number}`

## Control Rules
- Report and traceability endpoints are restricted to `Quality` and `Admin` roles.
- Quality report directories are auto-created at application startup.
- Batch traceability starts from existing inventory batch records and fails fast when batch is unknown.
- NCR defect categorization is optional but supported for analytics and filtering.

## Validation Checklist
- `GET /api/v1/quality/ncr`, `GET /api/v1/quality/capa`, and `GET /api/v1/quality/gauge` return HTTP `200`.
- Report endpoints return downloadable PDFs (`application/pdf`) for valid IDs.
- Trace endpoints return linked records across Stores/Purchase/Production/Sales.
- Schema mismatch checks:
  - `alembic current` is at head
  - `ncrs.defect_category` column exists

## Operational Notes
- If Quality endpoints fail after deployment with missing-column errors, run migrations before app startup.
- Traceability report filenames sanitize batch text for filesystem-safe output.
