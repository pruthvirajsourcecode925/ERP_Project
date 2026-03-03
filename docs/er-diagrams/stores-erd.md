# Stores Module ER Diagram

[← Back to ERD Index](index.md)

```mermaid
erDiagram
    users ||--o{ storage_locations : created_by_updated_by
    users ||--o{ grns : created_by_updated_by_received_by
    users ||--o{ grn_items : created_by_updated_by
    users ||--o{ rmir_reports : inspected_by
    users ||--o{ mtc_verifications : verified_by
    users ||--o{ batch_inventories : created_by_updated_by
    users ||--o{ stock_ledger : created_by_updated_by

    purchase_orders ||--o{ grns : has
    suppliers ||--o{ grns : supplies

    grns ||--o{ grn_items : has
    grn_items ||--o| rmir_reports : has
    grn_items ||--o| mtc_verifications : has

    grn_items ||--o| batch_inventories : batch_source
    storage_locations ||--o{ batch_inventories : stores

    batch_inventories ||--o{ stock_ledger : ledger_entries
    storage_locations ||--o{ stock_ledger : location_txn

    storage_locations {
        bigint id PK
        varchar location_code UK
        varchar location_name
        text description "nullable"
        bool is_active
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    grns {
        bigint id PK
        varchar grn_number UK
        bigint purchase_order_id FK
        bigint supplier_id FK
        int received_by FK
        timestamptz received_datetime
        date grn_date
        enum status "Draft|UnderInspection|Accepted|Rejected"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    grn_items {
        bigint id PK
        bigint grn_id FK
        varchar item_code
        text description "nullable"
        varchar heat_number "nullable"
        varchar batch_number UK
        numeric received_quantity
        numeric accepted_quantity
        numeric rejected_quantity
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    rmir_reports {
        bigint id PK
        bigint grn_item_id FK UK
        date inspection_date
        int inspected_by FK
        enum inspection_status "Pending|Accepted|Rejected"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    mtc_verifications {
        bigint id PK
        bigint grn_item_id FK UK
        varchar mtc_number
        bool chemical_composition_verified
        bool mechanical_properties_verified
        bool standard_compliance_verified
        int verified_by FK
        date verification_date
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    batch_inventories {
        bigint id PK
        varchar batch_number FK UK
        bigint storage_location_id FK
        varchar item_code
        numeric current_quantity
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    stock_ledger {
        bigint id PK
        varchar batch_number FK
        bigint storage_location_id FK
        enum transaction_type "GRN|ISSUE"
        varchar reference_number
        numeric quantity_in
        numeric quantity_out
        numeric balance_after
        timestamptz transaction_date
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }
```

## Notes
- GRN creation requires `storage_location_id` (must exist and be active).
- GRN stores receiving traceability via `received_by` and `received_datetime`.
- RMIR acceptance requires explicit `storage_location_id`; no DEFAULT fallback.
- Batch traceability format is enforced: `DRW-XXXX / SO-XX-XXX / CUST-XXX / HEAT-XX`.
- Deleting a location is soft-delete only and blocked when positive stock exists at that location.

## Navigation
- Previous: [Purchase ERD](purchase-erd.md)
- Next: [Auth & RBAC ERD](auth-rbac-erd.md)
- Index: [ER Diagram Index](index.md)
