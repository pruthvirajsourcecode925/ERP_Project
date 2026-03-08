# Dispatch Operations SOP (Backend API)

## Purpose
Defines the backend dispatch flow for shipment preparation, shipping-document generation, checklist control, release gating, and dispatch PDF retrieval.

## Preconditions
- Authenticated user with `Admin`, `Dispatch`, `Sales`, or `Quality` role plus `dispatch` module access.
- A valid released sales order exists.
- Linked production orders have passed final inspection before dispatch release.
- Certificate of conformity exists for the linked production order before dispatch release.

## Standard Flow
1. Create dispatch order: `POST /api/v1/dispatch/order`.
2. Review open dispatch orders: `GET /api/v1/dispatch/order`.
3. Add dispatch line items: `POST /api/v1/dispatch/order/{id}/item`.
4. Record checklist verification: `POST /api/v1/dispatch/order/{id}/checklist`.
5. Generate packing list: `POST /api/v1/dispatch/packing-list`.
6. Generate commercial invoice: `POST /api/v1/dispatch/invoice`.
7. Generate delivery challan: `POST /api/v1/dispatch/challan`.
8. Download invoice PDF: `GET /api/v1/dispatch/report/invoice/{dispatch_order_id}`.
9. Download challan PDF: `GET /api/v1/dispatch/report/challan/{dispatch_order_id}`.
10. Release shipment: `PATCH /api/v1/dispatch/order/{id}/ship`.

## Control Rules
- Dispatch orders cannot be modified after terminal release state.
- Dispatch item quantity must be positive.
- Checklist completion accepts only `completed` or `waived` states for release readiness.
- Release is blocked unless:
  - at least one dispatch item exists
  - every linked production order has passed final inspection
  - a linked certificate of conformity exists and matches a dispatched production order
  - a packing list exists
  - an invoice exists
  - a delivery challan exists
- Generated dispatch PDFs must remain inside `storage/dispatch_documents`.

## Validation Checklist
- `POST /api/v1/dispatch/order` returns `201` for an authorized user.
- `POST /api/v1/dispatch/order/{id}/item` rejects mismatched sales-order linkage.
- `PATCH /api/v1/dispatch/order/{id}/ship` fails when checklist approval is missing.
- `PATCH /api/v1/dispatch/order/{id}/ship` fails when CoC is missing.
- PDF endpoints return `application/pdf` and filesystem-safe filenames.
- Non-dispatch users without module access receive `403`.

## Operational Notes
- Dispatch output files are generated under:
  - `storage/dispatch_documents/invoices`
  - `storage/dispatch_documents/challans`
- `released` is the shipped-equivalent terminal status in the current dispatch model.
- Shipment tracking is modeled but optional in the current API flow.