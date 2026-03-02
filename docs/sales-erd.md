# Sales Module ER Diagram

This ERD reflects the currently validated foreign-key relationships in the Sales module.

```mermaid
erDiagram
    USERS {
        int id PK
    }

    ROLES {
        int id PK
    }

    CUSTOMERS {
        int id PK
        int created_by FK
        int updated_by FK
    }

    ENQUIRIES {
        int id PK
        int customer_id FK
        int created_by FK
        int updated_by FK
    }

    CONTRACT_REVIEWS {
        int id PK
        int enquiry_id FK
        int prepared_by FK
        int reviewed_by FK
        int approved_by FK
        int created_by FK
        int updated_by FK
    }

    QUOTATIONS {
        int id PK
        int contract_review_id FK
        int customer_id FK
        int prepared_by FK
        int approved_by FK
        int created_by FK
        int updated_by FK
    }

    QUOTATION_ITEMS {
        int id PK
        int quotation_id FK
        int created_by FK
        int updated_by FK
    }

    CUSTOMER_PO_REVIEWS {
        int id PK
        int quotation_id FK
        int reviewed_by FK
        int created_by FK
        int updated_by FK
    }

    SALES_ORDERS {
        int id PK
        int quotation_id FK
        int customer_po_review_id FK
        int created_by FK
        int updated_by FK
    }

    QUOTATION_TERMS_SETTINGS {
        int id PK
        int created_by FK
        int updated_by FK
    }

    USERS ||--o{ CUSTOMERS : creates_or_updates
    USERS ||--o{ ENQUIRIES : creates_or_updates
    USERS ||--o{ CONTRACT_REVIEWS : prepares_reviews_approves
    USERS ||--o{ CONTRACT_REVIEWS : creates_or_updates
    USERS ||--o{ QUOTATIONS : prepares_or_approves
    USERS ||--o{ QUOTATIONS : creates_or_updates
    USERS ||--o{ QUOTATION_ITEMS : creates_or_updates
    USERS ||--o{ CUSTOMER_PO_REVIEWS : reviews_creates_updates
    USERS ||--o{ SALES_ORDERS : creates_or_updates
    USERS ||--o{ QUOTATION_TERMS_SETTINGS : creates_or_updates

    ROLES ||--o{ USERS : assigned_role

    CUSTOMERS ||--o{ ENQUIRIES : has
    ENQUIRIES ||--o{ CONTRACT_REVIEWS : drives
    CONTRACT_REVIEWS ||--o{ QUOTATIONS : produces
    QUOTATIONS ||--o{ QUOTATION_ITEMS : contains
    QUOTATIONS ||--o{ CUSTOMER_PO_REVIEWS : reviewed_by_customer_po
    QUOTATIONS ||--o{ SALES_ORDERS : becomes
    CUSTOMER_PO_REVIEWS ||--o{ SALES_ORDERS : supports
```

## Notes

- `ROLES -> USERS` is included for completeness of auth/data ownership context.
- `QUOTATION_TERMS_SETTINGS` is global settings storage (not tied to a quotation row), but keeps user audit links.
- Cardinalities are modeled from FK directions currently present in the database schema.

## Contract Review Feasibility Checks

The sales flow enforces 5 mandatory contract-review checks. If any one is `False`, quotation creation and quotation PDF download are blocked.

Business label to backend field mapping:

- `drawing_available` -> `scope_clarity_ok`
- `special_process_identified` -> `capability_ok`
- `capacity_ok` -> `capacity_ok`
- `delivery_feasible` -> `delivery_commitment_ok`
- `quality_requirements_clear` -> `quality_requirements_ok`

When blocked, API returns an error listing which checkbox names are still not `True` so users can correct them before proceeding.
