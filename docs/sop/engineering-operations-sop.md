# Engineering Operations SOP (Backend API)

## Purpose
Defines the engineering backend flow for drawing control, revision management, route card release, and route card document traceability.

## Preconditions
- Authenticated user with `Engineering` or `Admin` role.
- A valid sales order and drawing revision are available before creating a route card.
- Route card file upload is mandatory during route card creation.

## Standard Flow
1. Create drawing: `POST /api/v1/engineering/drawing`.
2. Update drawing if needed: `PATCH /api/v1/engineering/drawing/{drawing_id}`.
3. Create drawing revision: `POST /api/v1/engineering/drawing/{drawing_id}/revision`.
4. Optionally update non-current, non-approved revision:
	- `PATCH /api/v1/engineering/drawing/{drawing_id}/revision/{revision_id}`.
5. Create route card with multipart upload:
	- `POST /api/v1/engineering/route-card`
	- Required form fields: `route_number`, `drawing_revision_id`, `sales_order_id`, `file`.
6. Add operations to route card:
	- `POST /api/v1/engineering/route-card/{route_card_id}/operation`.
7. Review route card and operations:
	- `GET /api/v1/engineering/route-card`
	- `GET /api/v1/engineering/route-card/{route_card_id}`.
8. Release route card:
	- `POST /api/v1/engineering/route-card/{route_card_id}/release`.
9. Download route card document:
	- By id: `GET /api/v1/engineering/route-card/{route_card_id}/document/download`
	- By traceability key: `GET /api/v1/engineering/route-card/document/download?traceability={route_number_or_so_or_po}`.
10. Mark obsolete when superseded:
	 - `PATCH /api/v1/engineering/route-card/{route_card_id}/obsolete`.

## Control Rules
- Route card upload cannot be empty.
- Route card creation enforces a valid drawing revision and sales-order linkage.
- Current or approved drawing revisions cannot be edited.
- Route card documents are constrained to `imports/route_cards` for secure downloads.
- Release operations are role-protected and audit logged.

## Validation Checklist
- `POST /api/v1/engineering/route-card` fails when file is missing or empty.
- `GET /api/v1/engineering/route-card/{id}/document/download` returns `404` when file metadata exists but file is missing.
- `PATCH /api/v1/engineering/drawing/{drawing_id}/revision/{revision_id}` rejects current/approved revisions.
- `POST /api/v1/engineering/route-card/{id}/release` transitions route card state to `released`.

## Traceability Notes
- Route card metadata persists:
  - `route_card_file_name`
  - `route_card_file_path`
  - `route_card_file_uploaded_at`
  - `route_card_file_content_type`
- Route card document retrieval by traceability supports search across route number and linked order references.
