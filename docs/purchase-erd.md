# Purchase Module ER Diagram

This ERD reflects the current Purchase module backend.

```mermaid
erDiagram
    users ||--o{ suppliers : created_by_updated_by
    users ||--o{ purchase_orders : created_by_updated_by
    users ||--o{ purchase_order_items : created_by_updated_by

    suppliers ||--o{ purchase_orders : has
    purchase_orders ||--o{ purchase_order_items : has

    sales_orders ||--o{ purchase_orders : optional_reference

    suppliers {
        bigint id PK
        varchar supplier_code UK
        varchar supplier_name
        varchar contact_person
        varchar phone
        varchar email
        text address
        boolean is_approved
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
        int created_by FK
        int updated_by FK
        boolean is_deleted
    }

    purchase_orders {
        bigint id PK
        varchar po_number UK
        bigint supplier_id FK
        bigint sales_order_id FK "nullable"
        date po_date
        date expected_delivery_date "nullable"
        enum status "draft|issued|closed"
        numeric total_amount
        text remarks
        timestamptz created_at
        timestamptz updated_at
        int created_by FK
        int updated_by FK
        boolean is_deleted
    }

    purchase_order_items {
        bigint id PK
        bigint purchase_order_id FK
        text description
        numeric quantity
        numeric unit_price
        numeric line_total
        timestamptz created_at
        timestamptz updated_at
        int created_by FK
        int updated_by FK
        boolean is_deleted
    }
```

## Notes
- Soft delete is implemented using `is_deleted` on all Purchase tables.
- `purchase_orders.status` lifecycle: `draft -> issued -> closed`.
- `purchase_order_items` are editable only while PO is in `draft`.
- `total_amount` is recalculated from non-deleted PO items.
