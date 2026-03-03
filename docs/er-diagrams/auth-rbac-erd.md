# Auth & RBAC ER Diagram

[← Back to ERD Index](index.md)

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
    }

    role_module_access {
        int id PK
        int role_id FK
        varchar module_key
        timestamptz created_at
    }

    users {
        int id PK
        varchar username UK
        varchar email UK
        varchar password_hash
        int role_id FK
        enum auth_provider "local|google|both"
        boolean is_active
        boolean is_locked
        int failed_attempts
        int created_by FK "nullable self"
        int updated_by FK "nullable self"
        boolean is_deleted
    }

    refresh_tokens {
        int id PK
        int user_id FK
        varchar token_hash UK
        timestamptz expires_at
        timestamptz revoked_at "nullable"
        varchar revoked_reason "nullable"
    }

    oauth_states {
        int id PK
        varchar provider
        varchar state UK
        timestamptz expires_at
        timestamptz consumed_at "nullable"
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
```

## Notes
- `oauth_states` is standalone state-tracking for OAuth flow (no FK to users).
- `role_module_access` enables multi-module permissions per role.
