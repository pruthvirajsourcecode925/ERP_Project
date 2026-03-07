# Auth and RBAC ER Diagram

[Back to ERD Index](index.md)

```mermaid
erDiagram
    roles ||--o{ users : assigned
    roles ||--o{ role_module_access : has_modules

    users ||--o{ refresh_tokens : has
    users ||--o{ audit_logs : actor

    roles {
        int id PK
        varchar name UK
        varchar description
        boolean is_active
        datetime created_at
        datetime updated_at
    }

    role_module_access {
        int id PK
        int role_id FK
        varchar module_key
        datetime created_at
    }

    users {
        int id PK
        varchar username UK
        varchar email UK
        varchar password_hash
        int role_id FK
        string auth_provider "local|google|both"
        boolean is_active
        boolean is_locked
        int failed_attempts
        datetime created_at
        datetime updated_at
        int created_by FK "nullable self"
        int updated_by FK "nullable self"
        boolean is_deleted
    }

    refresh_tokens {
        int id PK
        int user_id FK
        varchar token_hash UK
        datetime expires_at
        datetime revoked_at "nullable"
        varchar revoked_reason "nullable"
    }

    oauth_states {
        int id PK
        varchar provider
        varchar state UK
        datetime expires_at
        datetime consumed_at "nullable"
    }

    audit_logs {
        int id PK
        int user_id FK "nullable"
        varchar action
        varchar table_name "nullable"
        int record_id "nullable"
        text old_value "nullable"
        text new_value "nullable"
        datetime timestamp
    }
```

## Notes
- `oauth_states` is standalone state-tracking for OAuth flow and does not reference `users`.
- `role_module_access` enables admin-approved multi-module access per role.
- Current valid module keys include `auth`, `users`, `roles`, `sales`, `purchase`, `stores`, `engineering`, `quality`, `production`, `maintenance`, and `dispatch`.
- Default business-role mappings include `Sales`, `Purchase`, `Stores`, `Engineering`, and `Production`.
- Inactive roles block authentication and protected API access even if the user record itself is active.
- User creation and role/module management are admin-governed operations; there is no public registration route in the current backend.

## Navigation
- Previous: [Purchase ERD](purchase-erd.md)
- Next: [Engineering ERD](engineering-erd.md)
- Index: [ER Diagram Index](index.md)
