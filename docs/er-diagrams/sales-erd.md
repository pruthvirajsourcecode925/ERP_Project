# Sales Module ER Diagram

[← Back to ERD Index](index.md)

```mermaid
erDiagram
    users ||--o{ customers : created_by_updated_by
    users ||--o{ enquiries : created_by_updated_by
    users ||--o{ contract_reviews : generated_reviewed_created_updated
    users ||--o{ quotations : generated_created_updated
    users ||--o{ quotation_items : created_updated
    users ||--o{ customer_po_reviews : generated_reviewed_created_updated
    users ||--o{ sales_orders : created_updated
    users ||--o{ quotation_terms_settings : created_updated

    customers ||--o{ enquiries : has
    customers ||--o{ quotations : has
    customers ||--o{ sales_orders : has

    enquiries ||--o| contract_reviews : one_review
    enquiries ||--o{ quotations : has
    enquiries ||--o{ sales_orders : has

    contract_reviews ||--o{ quotations : used_by
    contract_reviews ||--o{ sales_orders : used_by

    quotations ||--o{ quotation_items : has
    quotations ||--o{ customer_po_reviews : has
    quotations ||--o{ sales_orders : referenced_by

    customer_po_reviews ||--o{ sales_orders : referenced_by

    customers {
        bigint id PK
        varchar customer_code UK
        varchar name
        varchar email
        varchar phone
        text billing_address
        text shipping_address
        boolean is_active
    }

    enquiries {
        bigint id PK
        varchar enquiry_number UK
        bigint customer_id FK
        date enquiry_date
        date requested_delivery_date "nullable"
        varchar currency
        text notes "nullable"
        enum status "draft|submitted|under_review|closed|cancelled"
    }

    contract_reviews {
        bigint id PK
        varchar document_number UK
        int revision
        timestamptz generated_at
        bigint generated_by FK "nullable"
        bigint enquiry_id FK "unique"
        enum status "pending|approved|rejected"
        bool scope_clarity_ok
        bool capability_ok
        bool capacity_ok
        bool delivery_commitment_ok
        bool quality_requirements_ok
        text review_comments "nullable"
        bigint reviewed_by FK "nullable"
        timestamptz reviewed_at "nullable"
    }

    quotations {
        bigint id PK
        varchar document_number UK
        int revision
        timestamptz generated_at
        bigint generated_by FK "nullable"
        varchar quotation_number UK
        bigint enquiry_id FK
        bigint contract_review_id FK
        bigint customer_id FK
        date issue_date
        date valid_until
        varchar currency
        numeric subtotal
        numeric tax_amount
        numeric total_amount
        text pdf_url "nullable"
        enum status "draft|issued|accepted|rejected|expired"
    }

    quotation_items {
        bigint id PK
        bigint quotation_id FK
        int line_no
        varchar item_code
        text description
        varchar uom
        numeric quantity
        numeric unit_price
        numeric line_total
    }

    quotation_terms_settings {
        bigint id PK
        text terms_json
    }

    customer_po_reviews {
        bigint id PK
        varchar document_number UK
        int revision
        timestamptz generated_at
        bigint generated_by FK "nullable"
        bigint quotation_id FK
        varchar customer_po_number
        date customer_po_date
        bool accepted
        enum status "pending|accepted|rejected"
        text deviation_notes "nullable"
        bigint reviewed_by FK "nullable"
        timestamptz reviewed_at "nullable"
    }

    sales_orders {
        bigint id PK
        varchar sales_order_number UK
        bigint customer_id FK
        bigint enquiry_id FK
        bigint contract_review_id FK
        bigint quotation_id FK
        bigint customer_po_review_id FK
        date order_date
        varchar currency
        numeric total_amount
        enum status "draft|confirmed|released|closed|cancelled"
    }
```

## Notes
- Quotation creation/download is gated by all 5 contract review feasibility flags.
- `valid_until >= issue_date` is enforced at DB level for quotations.
- `quotation_items` enforces unique `(quotation_id, line_no)`.

## Navigation
- Previous: [Engineering ERD](engineering-erd.md)
- Next: [Purchase ERD](purchase-erd.md)
- Index: [ER Diagram Index](index.md)
