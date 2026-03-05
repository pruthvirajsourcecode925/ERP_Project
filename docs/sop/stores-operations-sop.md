# Stores Operations SOP (Backend API)

## Purpose
This SOP defines the standard API sequence for Stores receiving, inspection, inventory posting, and issue with traceability controls.

## Preconditions
- Authenticated user with `Stores` or `Admin` role.
- Purchase Order is in `Issued` status.
- Active storage location exists.

## Standard Flow
1. Create storage location (`POST /api/v1/stores/location`) if required.
2. Create GRN (`POST /api/v1/stores/grn`) with mandatory `storage_location_id`.
3. Add GRN item (`POST /api/v1/stores/grn/{id}/item`) using traceable batch format:
   - `DRW-XXXX / SO-XX-XXX / CUST-XXX / HEAT-XX`
4. Create MTC verification (`POST /api/v1/stores/grn/{id}/mtc`).
5. Perform RMIR inspection (`POST /api/v1/stores/grn/{id}/inspect`):
   - If status is `Accepted`, `storage_location_id` is mandatory.
6. Issue material (`POST /api/v1/stores/issue`) with `batch_number`, `storage_location_id`, and `issue_quantity`.

## Control Rules
- Inactive or missing location blocks GRN creation and Accepted RMIR/issue operations.
- Accepted RMIR cannot proceed without MTC verification.
- Location deletion is soft-delete only and blocked if stock exists.
- GRN records receiving traceability with:
  - `received_by`
  - `received_datetime`

## Validation Checklist
- `POST /api/v1/stores/grn` rejects missing `storage_location_id`.
- `POST /api/v1/stores/grn/{id}/inspect` rejects Accepted status without `storage_location_id`.
- Invalid batch format is rejected with clear error message.
- Stock ledger entries are generated for GRN and ISSUE events.
