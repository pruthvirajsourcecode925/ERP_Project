# Postman Collections Guide

This guide explains how to import and execute the Postman collections under `docs/postman/`.

## Prerequisites
- API is running at `http://127.0.0.1:8000` (or update `baseUrl`).
- Database schema is up to date:

```powershell
alembic upgrade head
```

- You have an access token from the Auth collection.

## Import Order
1. `AS9100D-Auth-Lifecycle.postman_collection.json`
2. `AS9100D-Users-Roles-Admin.postman_collection.json`
3. `AS9100D-Admin-Dashboard.postman_collection.json`
3. Business flows:
   - `AS9100D-Dispatch-Lifecycle.postman_collection.json`
   - `AS9100D-Sales-Lifecycle.postman_collection.json`
   - `AS9100D-Purchase-Lifecycle.postman_collection.json`
   - `AS9100D-Engineering-RouteCard-Lifecycle.postman_collection.json`
   - `AS9100D-Stores-Lifecycle.postman_collection.json`
   - `AS9100D-Production-Lifecycle.postman_collection.json`
   - `AS9100D-Quality-Lifecycle.postman_collection.json`
   - `AS9100D-Maintenance-Lifecycle.postman_collection.json`

## Shared Variables
Set these at collection/environment level:
- `baseUrl`: API host, default `http://127.0.0.1:8000`
- `access_token`: Bearer token from login

Some flows also need seeded IDs (for example `customer_id`, `purchase_order_id`, `production_order_id`, `operation_id`, `machine_id`, `dispatch_order_id`, `coc_id`).

## Variable Naming Convention
- Use `_id` suffix for all identifier variables.
- Prefer domain-specific names over generic names. Examples:
   - `operator_id` (instead of `operator_user_id`)
   - `ncr_reference_id` (instead of `reference_id`)
   - `fir_inspection_id` (instead of generic `inspection_id`)

## Recommended Execution Sequence
1. Run Auth login and set `access_token`.
2. Run Sales, Purchase, Engineering, and Stores collections to seed linked records.
3. Run Production collection requests:
   - `Create Production Log`
   - reports (`batch`, `operator`, `machine`, `job`)
4. Run Quality collection requests:
   - NCR/CAPA/root-cause
   - gauge and audit plan/report
   - FAI create/get
   - traceability endpoints
   - PDF report download endpoints
5. Run Dispatch collection requests after a valid `sales_order_id`, `production_order_id`, and `coc_id` exist.
6. Run Admin dashboard collection with an admin token after functional data exists.

## Notes for Production Reports
- Production report endpoints use date filters as full UTC day ranges:
  - start: `start_date 00:00:00` (inclusive)
  - end: `end_date + 1 day 00:00:00` (exclusive)

## Notes for Quality Reports and Traceability
- Quality report output paths are under:
  - `storage/quality_reports/fir`
  - `storage/quality_reports/fai`
  - `storage/quality_reports/ncr`
  - `storage/quality_reports/capa`
  - `storage/quality_reports/audit`
  - `storage/quality_reports/traceability`
- If Quality endpoints fail with missing-column errors, run migrations before testing.

## Notes for Dispatch Documents
- Dispatch document output paths are under:
   - `storage/dispatch_documents/invoices`
   - `storage/dispatch_documents/challans`
- Dispatch release requires all of the following before `PATCH /api/v1/dispatch/order/{id}/ship` succeeds:
   - at least one dispatch item
   - a linked certificate of conformity
   - checklist approval
   - generated packing list, invoice, and challan
   - passed final inspection for linked production orders

## Notes for Admin Dashboards
- Admin dashboard routes are split by access level:
   - `Admin`: search, audit logs, alerts, alert settings
   - `Admin` or `Management`: summary and analytics endpoints
- Analytics endpoints are read models and may return empty arrays on fresh databases.

## Troubleshooting
- `401 Unauthorized`: verify `access_token` and role permissions.
- `404 not found`: verify referenced IDs exist and are not soft-deleted.
- `400 validation error`: check enum values and date formats in request bodies.
