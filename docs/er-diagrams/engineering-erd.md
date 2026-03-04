# Engineering Module ER Diagram

[← Back to ERD Index](index.md)

```mermaid
erDiagram
    users ||--o{ drawings : created_by_updated_by
    users ||--o{ drawing_revisions : approved_created_updated
    users ||--o{ route_cards : released_created_updated
    users ||--o{ route_operations : created_updated
    users ||--o{ special_processes : created_updated
    users ||--o{ route_operation_special_processes : created_updated
    users ||--o{ engineering_release_records : created_updated

    customers ||--o{ drawings : optional_reference
    sales_orders ||--o{ route_cards : referenced_by

    drawings ||--o{ drawing_revisions : has
    drawing_revisions ||--o{ route_cards : used_by
    route_cards ||--o{ route_operations : has
    route_cards ||--o{ engineering_release_records : has

    route_operations ||--o{ route_operation_special_processes : linked
    special_processes ||--o{ route_operation_special_processes : linked

    drawings {
        bigint id PK
        varchar drawing_number UK
        bigint customer_id FK "nullable"
        varchar part_name
        text description
        boolean is_active
    }

    drawing_revisions {
        bigint id PK
        bigint drawing_id FK
        varchar revision_code
        date revision_date
        text file_path
        boolean is_current
        bigint approved_by FK "nullable"
        timestamptz approved_date "nullable"
    }

    route_cards {
        bigint id PK
        varchar route_number UK
        bigint drawing_revision_id FK
        bigint sales_order_id FK
        enum status "draft|released|obsolete"
        bigint released_by FK "nullable"
        timestamptz released_date "nullable"
        varchar route_card_file_name "nullable"
        text route_card_file_path "nullable"
        timestamptz route_card_file_uploaded_at "nullable"
        varchar route_card_file_content_type "nullable"
    }

    route_operations {
        bigint id PK
        bigint route_card_id FK
        int operation_number
        varchar operation_name
        varchar work_center
        boolean inspection_required
        int sequence_order
    }

    special_processes {
        bigint id PK
        varchar process_name
        enum process_type "ht|plating|ndt|welding"
        boolean is_outsourced
    }

    route_operation_special_processes {
        bigint id PK
        bigint route_operation_id FK
        bigint special_process_id FK
    }

    engineering_release_records {
        bigint id PK
        bigint route_card_id FK
        enum release_status "approved|rejected"
        timestamptz release_date
        text remarks
    }
```

## Notes
- Uploaded/Imported Route Card PDFs are stored in a dedicated folder: `imports/route_cards`.
- `route_cards` stores document metadata (`route_card_file_name`, `route_card_file_path`, `route_card_file_uploaded_at`, `route_card_file_content_type`) for controlled download and traceability.

## Navigation
- Previous: [Auth & RBAC ERD](auth-rbac-erd.md)
- Next: [Sales ERD](sales-erd.md)
- Index: [ER Diagram Index](index.md)
