# Dispatch Module ER Diagram

[Back to ERD Index](index.md)

```mermaid
erDiagram
    users ||--o{ dispatch_orders : created_by_updated_by_released_by
    users ||--o{ dispatch_items : created_by_updated_by
    users ||--o{ dispatch_checklists : created_by_updated_by_checked_by
    users ||--o{ packing_lists : created_by_updated_by
    users ||--o{ dispatch_invoices : created_by_updated_by
    users ||--o{ delivery_challans : created_by_updated_by
    users ||--o{ shipment_trackings : created_by_updated_by

    sales_orders ||--o{ dispatch_orders : sales_order_id
    certificates_of_conformance ||--o{ dispatch_orders : certificate_of_conformance_id
    dispatch_orders ||--o{ dispatch_items : dispatch_order_id
    dispatch_orders ||--o{ dispatch_checklists : dispatch_order_id
    dispatch_orders ||--|| packing_lists : dispatch_order_id
    dispatch_orders ||--|| dispatch_invoices : dispatch_order_id
    dispatch_orders ||--|| delivery_challans : dispatch_order_id
    dispatch_orders ||--o{ shipment_trackings : dispatch_order_id
    production_orders ||--o{ dispatch_items : production_order_id

    dispatch_orders {
        bigint id PK
        varchar dispatch_number UK
        bigint sales_order_id FK
        bigint certificate_of_conformance_id FK "nullable"
        date dispatch_date
        enum status "draft|reviewed|released|hold|cancelled"
        int released_by FK "nullable"
        timestamptz released_at "nullable"
        varchar shipping_method "nullable"
        varchar destination "nullable"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    dispatch_items {
        bigint id PK
        bigint dispatch_order_id FK
        bigint production_order_id FK
        int line_number
        varchar item_code
        text description "nullable"
        numeric quantity
        varchar uom
        varchar lot_number "nullable"
        varchar serial_number "nullable"
        bool is_traceability_verified
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    dispatch_checklists {
        bigint id PK
        bigint dispatch_order_id FK
        varchar checklist_item
        varchar requirement_reference "nullable"
        enum status "pending|completed|failed|waived"
        int checked_by FK "nullable"
        timestamptz checked_at "nullable"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    packing_lists {
        bigint id PK
        varchar packing_list_number UK
        bigint dispatch_order_id FK UK
        date packed_date
        int package_count
        numeric gross_weight "nullable"
        numeric net_weight "nullable"
        varchar dimensions "nullable"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    dispatch_invoices {
        bigint id PK
        varchar invoice_number UK
        bigint dispatch_order_id FK UK
        date invoice_date
        varchar currency
        numeric subtotal
        numeric tax_amount
        numeric total_amount
        enum status "draft|issued|cancelled|paid"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    delivery_challans {
        bigint id PK
        varchar challan_number UK
        bigint dispatch_order_id FK UK
        date issue_date
        varchar received_by "nullable"
        timestamptz acknowledged_at "nullable"
        enum status "issued|in_transit|delivered|cancelled"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    shipment_trackings {
        bigint id PK
        bigint dispatch_order_id FK
        varchar tracking_number UK
        varchar carrier_name "nullable"
        date shipment_date
        date expected_delivery_date "nullable"
        date actual_delivery_date "nullable"
        enum status "booked|in_transit|delivered|exception"
        varchar proof_of_delivery_path "nullable"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }
```

## Key Rules
- `dispatch_items` enforce positive `line_number` and `quantity`, plus unique `(dispatch_order_id, line_number)`.
- `packing_lists`, `dispatch_invoices`, and `delivery_challans` are one-to-one with `dispatch_orders`.
- Dispatch completion requires at least one dispatch item, approved checklist state, linked CoC, and all three shipping documents.
- Shipment tracking is optional and supports multiple events per dispatch order.