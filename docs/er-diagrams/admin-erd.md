# Admin and Governance ER Diagram

[Back to ERD Index](index.md)

```mermaid
erDiagram
    users ||--o{ audit_logs : user_id
    users ||--o| alert_settings : created_by

    users {
        int id PK
        varchar username UK
        varchar email UK
        int role_id FK
        bool is_active
        bool is_locked
        bool is_deleted
    }

    audit_logs {
        int id PK
        int user_id FK "nullable"
        varchar action
        varchar table_name "nullable"
        int record_id "nullable"
        jsonb old_value "nullable"
        jsonb new_value "nullable"
        timestamptz timestamp
    }

    alert_settings {
        int id PK "singleton row, must be 1"
        bool alerts_enabled
        int created_by FK "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
```

## Tables

| Table | Description |
|---|---|
| `audit_logs` | Append-style operational audit trail consumed by the admin audit viewer. |
| `alert_settings` | Singleton dashboard alert configuration used to globally enable or disable alert generation. |

## Read Models
- Admin search does not create new tables; it queries `customers`, `suppliers`, `sales_orders`, `production_orders`, `batch_inventories`, and `dispatch_orders`.
- Admin summary and analytics endpoints are read models over existing sales, purchase, stores, production, quality, maintenance, dispatch, and user tables.

## Key Rules
- `alert_settings.id` is constrained to `1`, enforcing a single configuration row.
- Audit log viewer remains read-only from the admin API layer.
- Alerts are operational summaries derived from low stock, open breakdowns, pending dispatch, and open NCR conditions.