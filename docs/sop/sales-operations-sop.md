
## 1. Customer Management

## 2. Sales Order Lifecycle

## 3. Dispatch & Delivery

## 4. Invoicing

## 5. Best Practices


# Sales Module - Standard Operating Procedures (SOP)

## Purpose
Defines the standard API and process flow for customer management, sales order lifecycle, dispatch/delivery, and invoicing with validation and traceability controls.

## Preconditions
- Authenticated user with Sales or Admin role.
- Customer must be added and credit-checked before order acceptance.

## Standard Flow
1. **Customer Management**
	- Add/Update: `POST /api/v1/sales/customer` (details)
	- Credit check: `POST /api/v1/sales/customer/{id}/credit-check`
	- Log communication: `POST /api/v1/sales/customer/{id}/log`
2. **Sales Order Lifecycle**
	- Create: `POST /api/v1/sales/order` (item, quantity, price, delivery terms)
	- Approve: `POST /api/v1/sales/order/{id}/approve`
	- Amend/Cancel: `PATCH /api/v1/sales/order/{id}`
3. **Dispatch & Delivery**
	- Dispatch: `POST /api/v1/sales/dispatch` (order, shipment details)
	- Confirm delivery: `POST /api/v1/sales/delivery/{id}/confirm`
	- Handle returns: `POST /api/v1/sales/return` (order, reason)
4. **Invoicing**
	- Generate: `POST /api/v1/sales/invoice` (order, delivery confirmation)
	- Track payment: `POST /api/v1/sales/payment/track` (invoice)
	- Follow up: `POST /api/v1/sales/payment/followup` (overdue)

## Control Rules
- Only credit-checked customers can place orders.
- Sales order approval required before dispatch.
- Delivery confirmation required before invoicing.
- All actions are audit-logged.

## Validation Checklist
- Customer creation rejects missing details.
- Sales order creation rejects unapproved customers or missing fields.
- Dispatch rejects orders not approved or missing shipment details.
- Invoicing rejects unconfirmed deliveries.

## Traceability & Best Practices
- All customer, order, dispatch, and invoice actions are logged with user, timestamp, and action.
- Use system alerts for pending shipments or payments.
- Regularly review sales and payment reports for compliance.
