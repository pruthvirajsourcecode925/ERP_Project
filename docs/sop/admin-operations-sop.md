# Admin Operations SOP (Backend API)

## Purpose
Defines the backend operating flow for admin-only governance APIs, dashboard analytics, search, audit review, and configurable alerting.

## Preconditions
- Authenticated user with `Admin` access for search, audit, alerts, and alert settings.
- Authenticated user with `Admin` or `Management` access for summary and analytics endpoints.
- Database schema is current, including `alert_settings`.

## Search and Audit Flow
1. Run global search: `GET /api/v1/search?q={query}`.
2. Review audit logs: `GET /api/v1/admin/audit-logs`.
3. Optional audit filters:
   - `user_id`
   - `module`
   - `start_date`
   - `end_date`
   - `limit`

## Dashboard Summary and Analytics Flow
1. Get summary cards: `GET /api/v1/dashboard/summary`.
2. Get production trend: `GET /api/v1/dashboard/production-trend`.
3. Get quality distribution: `GET /api/v1/dashboard/quality-distribution`.
4. Get dispatch trend: `GET /api/v1/dashboard/dispatch-trend`.
5. Get supplier performance: `GET /api/v1/dashboard/supplier-performance`.
6. Get machine utilization: `GET /api/v1/dashboard/machine-utilization`.
7. Get user performance: `GET /api/v1/dashboard/user-performance`.

## Alerting Flow
1. Review active alerts: `GET /api/v1/dashboard/alerts`.
2. Enable or disable dashboard alerts: `PATCH /api/v1/dashboard/alerts/settings`.
3. Supported alert sources:
   - low stock
   - open machine breakdowns
   - pending dispatch orders
   - open NCRs

## Control Rules
- Search and audit log APIs are admin-only.
- Alert review and alert setting changes are admin-only.
- Summary and analytics APIs allow `Admin` and `Management`.
- Alert settings are singleton-backed and must resolve to `id = 1`.
- Search and analytics endpoints are read-only aggregations and do not mutate operational data.

## Validation Checklist
- `GET /api/v1/search?q=test` returns `200` for admin and rejects unauthorized access.
- `GET /api/v1/admin/audit-logs` returns `200` for admin and rejects non-admin users.
- `GET /api/v1/dashboard/summary` returns the expected summary keys.
- Analytics endpoints return structured JSON and tolerate empty datasets.
- `PATCH /api/v1/dashboard/alerts/settings` persists the `alerts_enabled` toggle.
- `GET /api/v1/dashboard/alerts` returns `[]` when alerts are disabled.

## Operational Notes
- Analytics values are derived from existing business-module tables, not cached reporting tables.
- Empty arrays or zero counts are valid responses on newly initialized databases.
- Audit queries should prefer date filters and limits in higher-volume environments.