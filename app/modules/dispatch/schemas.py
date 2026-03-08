from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

try:
    from pydantic import BaseModel, ConfigDict
except ImportError:
    from pydantic import BaseModel
    ConfigDict = None

from app.modules.dispatch.models import (
    DeliveryChallanStatus,
    DispatchChecklistStatus,
    DispatchOrderStatus,
    InvoiceStatus,
)


class ORMResponseModel(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True


class DispatchOrderCreate(BaseModel):
    dispatch_number: str
    sales_order_id: int
    certificate_of_conformance_id: int | None = None
    dispatch_date: date
    status: DispatchOrderStatus = DispatchOrderStatus.DRAFT
    released_by: int | None = None
    released_at: datetime | None = None
    shipping_method: str | None = None
    destination: str | None = None
    remarks: str | None = None


class DispatchOrderResponse(ORMResponseModel):
    id: int
    dispatch_number: str
    sales_order_id: int
    certificate_of_conformance_id: int | None = None
    dispatch_date: date
    status: DispatchOrderStatus
    released_by: int | None = None
    released_at: datetime | None = None
    shipping_method: str | None = None
    destination: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    is_deleted: bool


class DispatchItemCreate(BaseModel):
    dispatch_order_id: int
    production_order_id: int
    line_number: int
    item_code: str
    description: str | None = None
    quantity: Decimal
    uom: str
    lot_number: str | None = None
    serial_number: str | None = None
    is_traceability_verified: bool = False
    remarks: str | None = None


class DispatchItemResponse(ORMResponseModel):
    id: int
    dispatch_order_id: int
    production_order_id: int
    line_number: int
    item_code: str
    description: str | None = None
    quantity: Decimal
    uom: str
    lot_number: str | None = None
    serial_number: str | None = None
    is_traceability_verified: bool
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    is_deleted: bool


class PackingListCreate(BaseModel):
    packing_list_number: str
    dispatch_order_id: int
    packed_date: date
    package_count: int = 1
    gross_weight: Decimal | None = None
    net_weight: Decimal | None = None
    dimensions: str | None = None
    remarks: str | None = None


class PackingListResponse(ORMResponseModel):
    id: int
    packing_list_number: str
    dispatch_order_id: int
    packed_date: date
    package_count: int
    gross_weight: Decimal | None = None
    net_weight: Decimal | None = None
    dimensions: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    is_deleted: bool


class InvoiceCreate(BaseModel):
    invoice_number: str
    dispatch_order_id: int
    invoice_date: date
    currency: str
    subtotal: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    status: InvoiceStatus = InvoiceStatus.DRAFT
    remarks: str | None = None


class InvoiceResponse(ORMResponseModel):
    id: int
    invoice_number: str
    dispatch_order_id: int
    invoice_date: date
    currency: str
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status: InvoiceStatus
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    is_deleted: bool


class DeliveryChallanCreate(BaseModel):
    challan_number: str
    dispatch_order_id: int
    issue_date: date
    received_by: str | None = None
    acknowledged_at: datetime | None = None
    status: DeliveryChallanStatus = DeliveryChallanStatus.ISSUED
    remarks: str | None = None


class DeliveryChallanResponse(ORMResponseModel):
    id: int
    challan_number: str
    dispatch_order_id: int
    issue_date: date
    received_by: str | None = None
    acknowledged_at: datetime | None = None
    status: DeliveryChallanStatus
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    is_deleted: bool


class DispatchChecklistCreate(BaseModel):
    dispatch_order_id: int
    checklist_item: str
    requirement_reference: str | None = None
    status: DispatchChecklistStatus = DispatchChecklistStatus.PENDING
    checked_by: int | None = None
    checked_at: datetime | None = None
    remarks: str | None = None


class DispatchChecklistResponse(ORMResponseModel):
    id: int
    dispatch_order_id: int
    checklist_item: str
    requirement_reference: str | None = None
    status: DispatchChecklistStatus
    checked_by: int | None = None
    checked_at: datetime | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    is_deleted: bool