# Maintenance Module ER Diagram

[Back to ERD Index](index.md)

```mermaid
erDiagram
    users ||--o{ maintenance_machines : created_by_updated_by
    users ||--o{ machine_histories : created_by_updated_by
    users ||--o{ preventive_maintenance_plans : created_by_updated_by
    users ||--o{ preventive_maintenance_records : created_by_updated_by
    users ||--o{ breakdown_reports : created_by_updated_by
    users ||--o{ maintenance_work_orders : created_by_updated_by
    users ||--o{ machine_downtimes : created_by_updated_by

    maintenance_machines ||--o{ machine_histories : machine_history
    maintenance_machines ||--o{ preventive_maintenance_plans : pm_plans
    maintenance_machines ||--o{ preventive_maintenance_records : pm_records
    maintenance_machines ||--o{ breakdown_reports : breakdowns
    maintenance_machines ||--o{ maintenance_work_orders : work_orders
    maintenance_machines ||--o{ machine_downtimes : downtimes
    preventive_maintenance_plans ||--o{ preventive_maintenance_records : plan_records
    breakdown_reports ||--o{ maintenance_work_orders : breakdown_work_orders

    maintenance_machines {
        bigint id PK
        varchar machine_code UK "max 50"
        varchar machine_name "max 200"
        varchar work_center "max 100"
        varchar location "max 120, nullable"
        varchar manufacturer "max 120, nullable"
        varchar model "max 120, nullable"
        varchar serial_number "max 120, nullable"
        date commissioned_date "nullable"
        enum status "Active|Inactive|UnderMaintenance|Decommissioned"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    machine_histories {
        bigint id PK
        bigint machine_id FK
        enum event_type "Installed|Relocated|Upgraded|Calibration|StatusChange|Retired|Other"
        timestamptz event_datetime
        text previous_value "nullable"
        text new_value "nullable"
        text reason "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    preventive_maintenance_plans {
        bigint id PK
        bigint machine_id FK
        varchar plan_code UK "max 50"
        enum frequency_type "Daily|Weekly|Monthly|Quarterly|HalfYearly|Annual|RuntimeBased"
        int frequency_days "nullable"
        int runtime_interval_hours "nullable"
        text checklist_template "nullable"
        varchar standard_reference "max 120, nullable"
        date next_due_date "nullable"
        bool is_active
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    preventive_maintenance_records {
        bigint id PK
        bigint plan_id FK
        bigint machine_id FK
        date scheduled_date
        timestamptz performed_start_at "nullable"
        timestamptz performed_end_at "nullable"
        enum status "Planned|Completed|Deferred|Missed|PartiallyCompleted"
        text findings "nullable"
        text actions_taken "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    breakdown_reports {
        bigint id PK
        bigint machine_id FK
        varchar breakdown_number UK "max 50"
        timestamptz reported_at
        text symptom_description
        text probable_cause "nullable"
        enum severity "Minor|Major|Critical"
        enum status "Open|UnderInvestigation|Assigned|Resolved|Closed"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    maintenance_work_orders {
        bigint id PK
        varchar work_order_number UK "max 50"
        bigint breakdown_id FK
        bigint machine_id FK
        timestamptz planned_start_at "nullable"
        timestamptz actual_start_at "nullable"
        timestamptz actual_end_at "nullable"
        text root_cause "nullable"
        text repair_action "nullable"
        enum status "Created|Assigned|InProgress|Completed|Verified|Cancelled"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }

    machine_downtimes {
        bigint id PK
        bigint machine_id FK
        enum source_type "Breakdown|PreventiveMaintenance|Setup|Utilities|Other"
        bigint source_id "nullable"
        timestamptz downtime_start_at
        timestamptz downtime_end_at "nullable"
        int duration_minutes "nullable"
        bool is_planned
        varchar reason_code "max 80, nullable"
        text remarks "nullable"
        timestamptz created_at
        timestamptz updated_at
        int created_by FK "nullable"
        int updated_by FK "nullable"
        bool is_deleted
    }
```

## Tables

| Table | Description |
|---|---|
| `maintenance_machines` | Machine master for maintenance-tracked equipment. Tracks status lifecycle (Active, Inactive, UnderMaintenance, Decommissioned). |
| `machine_histories` | Immutable audit trail of machine lifecycle events (installation, relocation, calibration, status changes). |
| `preventive_maintenance_plans` | Scheduled preventive maintenance plans per machine with configurable frequency. |
| `preventive_maintenance_records` | Individual PM execution records linked to plans. |
| `breakdown_reports` | Unplanned breakdown incidents with severity classification. |
| `maintenance_work_orders` | Corrective work orders raised from breakdown reports. |
| `machine_downtimes` | Downtime records for both planned (PM) and unplanned (breakdown) events. |

## Key Relationships
- All child tables cascade-delete from `maintenance_machines`.
- `preventive_maintenance_records` link to both the parent plan and the machine.
- `maintenance_work_orders` link to both the originating breakdown report and the machine.
- `machine_downtimes.source_id` is a polymorphic reference (not enforced via FK) to breakdowns or PM records based on `source_type`.
- All tables carry `created_by`/`updated_by` audit columns referencing `users.id`.

## Cross-Module Integration
- Production service validates machine maintenance status before starting operations. If a maintenance machine has status `UnderMaintenance`, production operation start is blocked.
