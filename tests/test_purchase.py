from __future__ import annotations

import random
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.modules.purchase.models import PurchaseOrder
from app.services.purchase_service import (
    DEFAULT_SUPPLIER_QUALITY_REQUIREMENTS,
    save_purchase_order_document_path,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_admin_token() -> str:
    db = SessionLocal()
    admin_id = None
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
        if admin and admin_role:
            admin.password_hash = get_password_hash("Admin@12345")
            admin.role_id = admin_role.id
            admin.is_active = True
            admin.is_locked = False
            admin.failed_attempts = 0
            admin.auth_provider = "both"
            db.add(admin)
            db.commit()
            admin_id = admin.id
    finally:
        db.close()

    assert admin_id is not None
    return create_access_token(str(admin_id))


def _unique_code() -> str:
    return str(int(uuid4().hex[:8], 16))


def _create_supplier(token: str, *, is_approved: bool = False) -> dict:
    code = _unique_code()
    resp = client.post(
        "/api/v1/purchase/supplier",
        json={
            "supplier_code": f"SUP-{code}",
            "supplier_name": f"Supplier {code}",
            "contact_person": "Test Person",
            "phone": "9999999999",
            "email": f"sup{code}@example.com",
            "address": "123 Test St",
            "is_approved": is_approved,
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _approve_supplier(
    token: str,
    supplier_id: int,
    *,
    approved: bool = True,
    approval_remarks: str | None = "AS9100D 8.4 quality requirements acknowledged",
    quality_acknowledged: bool | None = True,
) -> dict:
    resp = client.post(
        f"/api/v1/purchase/supplier/{supplier_id}/approve",
        json={
            "approved": approved,
            "approval_remarks": approval_remarks,
            "quality_acknowledged": quality_acknowledged,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_po(token: str, supplier_id: int, *, quality_notes: str = "Supplier quality clauses acknowledged") -> dict:
    resp = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier_id,
            "po_date": date.today().isoformat(),
            "expected_delivery_date": None,
            "remarks": "Test PO",
            "quality_notes": quality_notes,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_item(token: str, po_id: int, *, quantity: str = "5", unit_price: str = "100.00") -> dict:
    resp = client.post(
        f"/api/v1/purchase/order/{po_id}/item",
        json={"description": "Test Item", "quantity": quantity, "unit_price": unit_price},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Supplier — create, duplicate, get, update, soft delete
# ---------------------------------------------------------------------------

def test_purchase_supplier_create_successfully():
    token = _get_admin_token()
    supplier = _create_supplier(token)
    assert supplier["id"] > 0
    assert supplier["is_approved"] is False


def test_purchase_supplier_duplicate_code_rejected():
    token = _get_admin_token()
    code = _unique_code()
    payload = {
        "supplier_code": f"DUP-{code}",
        "supplier_name": "Dup Supplier",
        "is_approved": False,
        "is_active": True,
    }
    r1 = client.post("/api/v1/purchase/supplier", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 201
    r2 = client.post("/api/v1/purchase/supplier", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 400


def test_purchase_supplier_get_by_id():
    token = _get_admin_token()
    supplier = _create_supplier(token)
    resp = client.get(f"/api/v1/purchase/supplier/{supplier['id']}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == supplier["id"]


def test_purchase_supplier_get_not_found():
    token = _get_admin_token()
    resp = client.get("/api/v1/purchase/supplier/999999999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_purchase_supplier_update():
    token = _get_admin_token()
    supplier = _create_supplier(token)
    resp = client.patch(
        f"/api/v1/purchase/supplier/{supplier['id']}",
        json={"supplier_name": "Updated Name", "is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["supplier_name"] == "Updated Name"
    assert body["is_active"] is False


def test_purchase_supplier_cannot_deactivate_with_open_po():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    _create_po(token, supplier["id"])

    resp = client.patch(
        f"/api/v1/purchase/supplier/{supplier['id']}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Cannot deactivate supplier with open purchase orders" in resp.json()["detail"]


def test_purchase_supplier_approve():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=False)
    assert supplier["is_approved"] is False

    approved = _approve_supplier(token, supplier["id"])
    assert approved["is_approved"] is True


def test_purchase_supplier_approve_requires_quality_acknowledged_true():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=False)

    resp = client.post(
        f"/api/v1/purchase/supplier/{supplier['id']}/approve",
        json={
            "approved": True,
            "approval_remarks": "Quality reviewed",
            "quality_acknowledged": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Quality acknowledgment must be True" in resp.json()["detail"]


def test_purchase_supplier_approve_requires_approval_remarks():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=False)

    resp = client.post(
        f"/api/v1/purchase/supplier/{supplier['id']}/approve",
        json={
            "approved": True,
            "approval_remarks": "   ",
            "quality_acknowledged": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Approval remarks are required" in resp.json()["detail"]


def test_purchase_supplier_approval_metadata_stored_correctly():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=False)

    approved = _approve_supplier(
        token,
        supplier["id"],
        approval_remarks="Approved for aerospace quality flow",
        quality_acknowledged=True,
    )

    assert approved["is_approved"] is True
    assert approved["quality_acknowledged"] is True
    assert approved["approval_remarks"] == "Approved for aerospace quality flow"
    assert approved["approval_date"] is not None
    assert approved["approved_by"] is not None


def test_purchase_supplier_soft_delete():
    token = _get_admin_token()
    supplier = _create_supplier(token)
    del_resp = client.delete(
        f"/api/v1/purchase/supplier/{supplier['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    get_resp = client.get(
        f"/api/v1/purchase/supplier/{supplier['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_purchase_supplier_cannot_delete_with_active_po():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    _create_po(token, supplier["id"])

    del_resp = client.delete(
        f"/api/v1/purchase/supplier/{supplier['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 400


def test_purchase_supplier_list_with_filters():
    token = _get_admin_token()
    _create_supplier(token, is_approved=False)
    resp = client.get(
        "/api/v1/purchase/supplier",
        params={"is_approved": False, "skip": 0, "limit": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# 2. PO — create rules, list, get detail
# ---------------------------------------------------------------------------

def test_purchase_po_requires_approved_supplier():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=False)
    resp = client.post(
        "/api/v1/purchase/order",
        json={"supplier_id": supplier["id"], "po_date": date.today().isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_purchase_po_create_successfully():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    assert po["status"] == "draft"
    assert po["total_amount"] == "0.00"


def test_purchase_po_create_applies_multiline_default_quality_requirements():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)

    resp = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier["id"],
            "po_date": date.today().isoformat(),
            "quality_notes": "Quality requirements accepted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    po = resp.json()
    assert po["supplier_quality_requirements"] == DEFAULT_SUPPLIER_QUALITY_REQUIREMENTS
    assert "\n" in po["supplier_quality_requirements"]


def test_purchase_po_duplicate_open_same_supplier_and_sales_order_blocked():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)

    first = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier["id"],
            "sales_order_id": None,
            "po_date": date.today().isoformat(),
            "quality_notes": "Quality requirements accepted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier["id"],
            "sales_order_id": None,
            "po_date": date.today().isoformat(),
            "quality_notes": "Quality requirements accepted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 400
    assert "Open PurchaseOrder already exists for this supplier and sales order" in second.json()["detail"]


def test_purchase_po_date_validation_expected_delivery_before_po_date_rejected():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)

    resp = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier["id"],
            "po_date": "2026-03-10",
            "expected_delivery_date": "2026-03-09",
            "quality_notes": "Quality requirements accepted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Expected delivery date must be on or after PO date" in resp.json()["detail"]


def test_purchase_po_creation_blocked_if_quality_notes_missing():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=False)
    _approve_supplier(token, supplier["id"])

    resp = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier["id"],
            "po_date": date.today().isoformat(),
            "quality_notes": "   ",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Quality notes are required" in resp.json()["detail"]


def test_purchase_po_list():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    _create_po(token, supplier["id"])
    resp = client.get(
        "/api/v1/purchase/order",
        params={"status": "draft", "skip": 0, "limit": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_purchase_po_get_detail():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    resp = client.get(f"/api/v1/purchase/order/{po['id']}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "items" in resp.json()


# ---------------------------------------------------------------------------
# 3. PO Items — add, line total auto-calc, remove, total recalculates
# ---------------------------------------------------------------------------

def test_purchase_po_item_add_successfully():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    item = _add_item(token, po["id"], quantity="10", unit_price="50.00")
    assert item["line_total"] == "500.00"


def test_purchase_po_item_line_total_is_server_calculated():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])

    resp = client.post(
        f"/api/v1/purchase/order/{po['id']}/item",
        json={
            "description": "Injected Line Total",
            "quantity": "2",
            "unit_price": "25.00",
            "line_total": "9999.99",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["line_total"] == "50.00"


def test_purchase_po_total_amount_recalculates_on_add():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"], quantity="2", unit_price="100.00")
    _add_item(token, po["id"], quantity="3", unit_price="50.00")

    detail = client.get(f"/api/v1/purchase/order/{po['id']}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    assert Decimal(detail.json()["total_amount"]) == Decimal("350.00")


def test_purchase_po_item_invalid_quantity_rejected():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    resp = client.post(
        f"/api/v1/purchase/order/{po['id']}/item",
        json={"description": "Bad Item", "quantity": "0", "unit_price": "10.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_purchase_po_item_negative_price_rejected():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    resp = client.post(
        f"/api/v1/purchase/order/{po['id']}/item",
        json={"description": "Bad Item", "quantity": "1", "unit_price": "-1.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_purchase_po_item_remove_and_total_recalculates():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    item1 = _add_item(token, po["id"], quantity="2", unit_price="100.00")
    _add_item(token, po["id"], quantity="3", unit_price="50.00")

    del_resp = client.delete(
        f"/api/v1/purchase/order/{po['id']}/item/{item1['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    detail = client.get(f"/api/v1/purchase/order/{po['id']}", headers={"Authorization": f"Bearer {token}"})
    assert Decimal(detail.json()["total_amount"]) == Decimal("150.00")
    active_items = [i for i in detail.json()["items"] if i["id"] != item1["id"]]
    assert len(active_items) == 1


def test_purchase_po_cannot_add_item_after_issue():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"])

    client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.post(
        f"/api/v1/purchase/order/{po['id']}/item",
        json={"description": "Late Item", "quantity": "1", "unit_price": "10.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_purchase_po_cannot_remove_item_after_issue():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    item = _add_item(token, po["id"])

    client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )

    del_resp = client.delete(
        f"/api/v1/purchase/order/{po['id']}/item/{item['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Status transitions
# ---------------------------------------------------------------------------

def test_purchase_po_issue_without_items_rejected():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    resp = client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_purchase_po_status_draft_to_issued():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"])

    resp = client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "issued"


def test_purchase_po_status_issued_to_closed():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"])

    client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


def test_purchase_po_invalid_status_transition_rejected():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    resp = client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 5. Soft delete PO
# ---------------------------------------------------------------------------

def test_purchase_po_soft_delete_draft():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])

    del_resp = client.delete(
        f"/api/v1/purchase/order/{po['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204


def test_purchase_po_soft_deleted_not_visible_in_list():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])

    client.delete(f"/api/v1/purchase/order/{po['id']}", headers={"Authorization": f"Bearer {token}"})

    resp = client.get(
        "/api/v1/purchase/order",
        params={"skip": 0, "limit": 200},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    ids = [o["id"] for o in resp.json()]
    assert po["id"] not in ids


def test_purchase_po_cannot_delete_issued():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"])

    client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )

    del_resp = client.delete(
        f"/api/v1/purchase/order/{po['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 400


def test_purchase_summary_endpoint_returns_counts():
    token = _get_admin_token()
    resp = client.get(
        "/api/v1/purchase/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "total_suppliers",
        "total_approved_suppliers",
        "total_draft_pos",
        "total_issued_pos",
        "total_closed_pos",
    }
    assert all(isinstance(body[k], int) for k in body)


def test_purchase_po_document_path_saved_only_once_on_first_generation():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])

    db = SessionLocal()
    try:
        first_saved = save_purchase_order_document_path(
            db,
            purchase_order_id=po["id"],
            generated_file_path="/tmp/po_first_generation.pdf",
        )
        assert first_saved.po_document_path == "/tmp/po_first_generation.pdf"

        second_attempt = save_purchase_order_document_path(
            db,
            purchase_order_id=po["id"],
            generated_file_path="/tmp/po_second_generation.pdf",
        )
        assert second_attempt.po_document_path == "/tmp/po_first_generation.pdf"
    finally:
        db.close()


def test_purchase_po_download_generates_once_and_reuses_stored_path():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"], quantity="2", unit_price="100.00")
    issue_resp = client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_resp.status_code == 200

    first_download = client.get(
        f"/api/v1/purchase/order/{po['id']}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first_download.status_code == 200
    assert "application/pdf" in first_download.headers.get("content-type", "")

    db = SessionLocal()
    try:
        po_record = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po["id"]))
        assert po_record is not None
        assert po_record.po_document_path is not None
        first_path = po_record.po_document_path
        first_file = Path(first_path).resolve()
        assert first_file.exists()
        assert first_file.name == f"{po['po_number']}.pdf"
        assert first_file.parent.name == "purchase_orders"
        assert first_file.parent.parent.name == "exports"
    finally:
        db.close()

    second_download = client.get(
        f"/api/v1/purchase/order/{po['id']}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_download.status_code == 200
    assert "application/pdf" in second_download.headers.get("content-type", "")

    db = SessionLocal()
    try:
        po_record = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po["id"]))
        assert po_record is not None
        assert po_record.po_document_path == first_path
    finally:
        db.close()


def test_purchase_po_download_rejected_for_draft_status():
    token = _get_admin_token()
    supplier = _create_supplier(token, is_approved=True)
    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"], quantity="1", unit_price="10.00")

    resp = client.get(
        f"/api/v1/purchase/order/{po['id']}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Issued or Closed" in resp.json()["detail"]


def test_download_purchase_order_pdf():
    token = _get_admin_token()

    supplier = _create_supplier(token, is_approved=False)
    approved_supplier = _approve_supplier(token, supplier["id"])
    assert approved_supplier["is_approved"] is True

    po = _create_po(token, supplier["id"])
    _add_item(token, po["id"], quantity="2", unit_price="100.00")

    issue_resp = client.put(
        f"/api/v1/purchase/order/{po['id']}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_resp.status_code == 200

    download_resp = client.get(
        f"/api/v1/purchase/order/{po['id']}/download",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert download_resp.status_code == 200
    assert "application/pdf" in download_resp.headers.get("content-type", "")
    content_disposition = download_resp.headers.get("content-disposition", "")
    assert po["po_number"] in content_disposition
    assert ".pdf" in content_disposition
