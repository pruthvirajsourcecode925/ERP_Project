
## 1. Supplier Management

## 2. Purchase Order Lifecycle

## 3. Goods Receipt

## 4. Invoice Processing

## 5. Best Practices


# Purchase Module - Standard Operating Procedures (SOP)

## Purpose
Defines the standard API and process flow for supplier management, purchase order lifecycle, goods receipt, and invoice processing with validation and traceability controls.

## Preconditions
- Authenticated user with Purchase or Admin role.
- Supplier must be approved before PO creation.

## Standard Flow
1. **Supplier Management**
	- Add: `POST /api/v1/purchase/supplier` (details, documents)
	- Approve: `POST /api/v1/purchase/supplier/{id}/approve`
	- Review: `GET /api/v1/purchase/supplier/performance`
2. **Purchase Order Lifecycle**
	- Create: `POST /api/v1/purchase/order` (supplier, items, price, quantity, terms)
	- Approve: `POST /api/v1/purchase/order/{id}/approve`
	- Amend/Cancel: `PATCH /api/v1/purchase/order/{id}`
3. **Goods Receipt**
	- Receive: `POST /api/v1/purchase/grn` (PO, items, inspection)
	- Record discrepancies: `POST /api/v1/purchase/grn/{id}/discrepancy`
	- Update inventory: automatic on acceptance
4. **Invoice Processing**
	- Match: `POST /api/v1/purchase/invoice/match` (PO, GRN, invoice)
	- Approve: `POST /api/v1/purchase/invoice/{id}/approve`
	- Maintain records for audit

## Control Rules
- Only approved suppliers can be used in POs.
- PO approval required before goods receipt.
- Discrepancies must be resolved before invoice approval.
- All actions are audit-logged.

## Validation Checklist
- Supplier creation rejects missing documents/details.
- PO creation rejects unapproved suppliers or missing fields.
- Goods receipt rejects items not matching PO.
- Invoice approval rejects unmatched or disputed items.

## Traceability & Best Practices
- All supplier, PO, GRN, and invoice actions are logged with user, timestamp, and action.
- Use system notifications for pending approvals.
- Maintain segregation of duties (request, approve, receive, pay).
