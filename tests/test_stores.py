from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.modules.stores.models import BatchInventory, StockLedger, StockTransactionType, StorageLocation

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_code(prefix: str = "X") -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def _traceable_batch_number() -> str:
    token = uuid4().hex.upper()
    return f"DRW-{token[:4]} / SO-{token[4:6]}-{token[6:9]} / CUST-{token[9:12]} / HEAT-{token[12:14]}"


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


def _get_admin_user_id() -> int:
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        return admin.id
    finally:
        db.close()


def _create_supplier(token: str) -> dict:
    code = _unique_code("SUP")
    resp = client.post(
        "/api/v1/purchase/supplier",
        json={
            "supplier_code": code,
            "supplier_name": f"Supplier {code}",
            "is_approved": False,
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _approve_supplier(token: str, supplier_id: int) -> dict:
    resp = client.post(
        f"/api/v1/purchase/supplier/{supplier_id}/approve",
        json={
            "approved": True,
            "approval_remarks": "AS9100D supplier quality approved",
            "quality_acknowledged": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_po(token: str, supplier_id: int) -> dict:
    resp = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier_id,
            "po_date": date.today().isoformat(),
            "quality_notes": "Supplier quality clauses accepted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_po_item(token: str, po_id: int) -> dict:
    resp = client.post(
        f"/api/v1/purchase/order/{po_id}/item",
        json={"description": "RM Item", "quantity": "10", "unit_price": "5.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _issue_po(token: str, po_id: int) -> dict:
    resp = client.put(
        f"/api/v1/purchase/order/{po_id}/status",
        json={"status": "issued"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_issued_po(token: str) -> tuple[dict, dict]:
    supplier = _create_supplier(token)
    _approve_supplier(token, supplier["id"])
    po = _create_po(token, supplier["id"])
    _add_po_item(token, po["id"])
    _issue_po(token, po["id"])
    return supplier, po


def _create_grn(token: str, po_id: int, supplier_id: int, storage_location_id: int | None = None) -> dict:
    if storage_location_id is None:
        location = _create_location(
            token,
            location_code=_unique_code("LOC"),
            location_name="Auto GRN Location",
            is_active=True,
        )
        storage_location_id = location["id"]

    grn_number = _unique_code("GRN")
    resp = client.post(
        "/api/v1/stores/grn",
        json={
            "grn_number": grn_number,
            "purchase_order_id": po_id,
            "supplier_id": supplier_id,
            "storage_location_id": storage_location_id,
            "grn_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_grn_item(
    token: str,
    grn_id: int,
    *,
    batch_number: str,
    received: str = "10.000",
    accepted: str = "8.000",
    rejected: str = "2.000",
) -> dict:
    resp = client.post(
        f"/api/v1/stores/grn/{grn_id}/item",
        json={
            "item_code": "RM-AL-001",
            "description": "Raw material",
            "heat_number": "HT-001",
            "batch_number": batch_number,
            "received_quantity": received,
            "accepted_quantity": accepted,
            "rejected_quantity": rejected,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_location(
    token: str,
    *,
    location_code: str,
    location_name: str,
    is_active: bool = True,
    description: str | None = None,
) -> dict:
    resp = client.post(
        "/api/v1/stores/location",
        json={
            "location_code": location_code,
            "location_name": location_name,
            "description": description,
            "is_active": is_active,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _ensure_default_location(token: str) -> dict:
    db = SessionLocal()
    try:
        default_location = db.scalar(select(StorageLocation).where(StorageLocation.location_code == "DEFAULT"))
        if default_location:
            default_location.is_deleted = False
            default_location.is_active = True
            db.add(default_location)
            db.commit()
            db.refresh(default_location)
            return {
                "id": default_location.id,
                "location_code": default_location.location_code,
                "location_name": default_location.location_name,
                "description": default_location.description,
                "is_active": default_location.is_active,
            }
    finally:
        db.close()

    return _create_location(
        token,
        location_code="DEFAULT",
        location_name="Default Location",
        is_active=True,
        description="Auto-assigned default location",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_stores_grn_creation_blocked_if_po_not_issued():
    token = _get_admin_token()
    supplier = _create_supplier(token)
    _approve_supplier(token, supplier["id"])
    po = _create_po(token, supplier["id"])
    location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Receiving Location",
        is_active=True,
    )

    resp = client.post(
        "/api/v1/stores/grn",
        json={
            "grn_number": _unique_code("GRN"),
            "purchase_order_id": po["id"],
            "supplier_id": supplier["id"],
            "storage_location_id": location["id"],
            "grn_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "PurchaseOrder status is Issued" in resp.json()["detail"]


def test_stores_grn_item_validation_accepted_plus_rejected_equals_received():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])

    resp = client.post(
        f"/api/v1/stores/grn/{grn['id']}/item",
        json={
            "item_code": "RM-AL-001",
            "description": "Raw material",
            "heat_number": "HT-002",
            "batch_number": _traceable_batch_number(),
            "received_quantity": "10.000",
            "accepted_quantity": "7.000",
            "rejected_quantity": "2.000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "must equal received quantity" in resp.json()["detail"]


def test_stores_mtc_required_before_rmir_acceptance():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    item = _add_grn_item(token, grn["id"], batch_number=_traceable_batch_number())

    resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Inspection accepted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "MTC verification is completed" in resp.json()["detail"]


def test_stores_stock_increases_only_after_rmir_accepted_and_batch_inventory_updated():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Inspection Location",
        is_active=True,
    )
    batch_number = _traceable_batch_number()
    item = _add_grn_item(token, grn["id"], batch_number=batch_number, accepted="6.000", rejected="4.000")

    pending_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Pending",
            "remarks": "Pending inspection",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pending_resp.status_code == 200

    db = SessionLocal()
    try:
        pending_inventory = db.scalar(
            select(BatchInventory).where(BatchInventory.batch_number == batch_number, BatchInventory.is_deleted.is_(False))
        )
        assert pending_inventory is None
    finally:
        db.close()

    mtc_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/mtc",
        json={
            "mtc_number": _unique_code("MTC"),
            "chemical_composition_verified": True,
            "mechanical_properties_verified": True,
            "standard_compliance_verified": True,
            "verification_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mtc_resp.status_code == 201

    accepted_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Accepted",
            "storage_location_id": location["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert accepted_resp.status_code == 200

    db = SessionLocal()
    try:
        inventory = db.scalar(
            select(BatchInventory).where(BatchInventory.batch_number == batch_number, BatchInventory.is_deleted.is_(False))
        )
        assert inventory is not None
        assert Decimal(str(inventory.current_quantity)) == Decimal("6.000")
    finally:
        db.close()


def test_stores_issue_blocked_if_insufficient_stock():
    token = _get_admin_token()
    default_location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Issue Location",
        is_active=True,
    )
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    batch_number = _traceable_batch_number()
    item = _add_grn_item(token, grn["id"], batch_number=batch_number, accepted="3.000", rejected="7.000")

    mtc_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/mtc",
        json={
            "mtc_number": _unique_code("MTC"),
            "chemical_composition_verified": True,
            "mechanical_properties_verified": True,
            "standard_compliance_verified": True,
            "verification_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mtc_resp.status_code == 201

    inspect_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Accepted",
            "storage_location_id": default_location["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inspect_resp.status_code == 200

    issue_resp = client.post(
        "/api/v1/stores/issue",
        json={
            "batch_number": batch_number,
            "storage_location_id": default_location["id"],
            "issue_quantity": "5.000",
            "reference_number": _unique_code("ISSUE"),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_resp.status_code == 400
    assert "Insufficient batch inventory quantity" in issue_resp.json()["detail"]


def test_stores_ledger_entries_created_for_grn_and_issue_and_inventory_updated_correctly():
    token = _get_admin_token()
    default_location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Ledger Location",
        is_active=True,
    )
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    batch_number = _traceable_batch_number()
    item = _add_grn_item(token, grn["id"], batch_number=batch_number, accepted="9.000", rejected="1.000")

    mtc_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/mtc",
        json={
            "mtc_number": _unique_code("MTC"),
            "chemical_composition_verified": True,
            "mechanical_properties_verified": True,
            "standard_compliance_verified": True,
            "verification_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mtc_resp.status_code == 201

    accept_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Accepted",
            "storage_location_id": default_location["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert accept_resp.status_code == 200

    issue_resp = client.post(
        "/api/v1/stores/issue",
        json={
            "batch_number": batch_number,
            "storage_location_id": default_location["id"],
            "issue_quantity": "4.000",
            "reference_number": _unique_code("ISSUE"),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_resp.status_code == 201

    db = SessionLocal()
    try:
        ledger_rows = db.scalars(
            select(StockLedger).where(StockLedger.batch_number == batch_number, StockLedger.is_deleted.is_(False))
        ).all()
        transaction_types = {row.transaction_type for row in ledger_rows}
        assert StockTransactionType.GRN in transaction_types
        assert StockTransactionType.ISSUE in transaction_types

        inventory = db.scalar(
            select(BatchInventory).where(BatchInventory.batch_number == batch_number, BatchInventory.is_deleted.is_(False))
        )
        assert inventory is not None
        assert Decimal(str(inventory.current_quantity)) == Decimal("5.000")
    finally:
        db.close()


def test_stores_create_location_successfully():
    token = _get_admin_token()
    location_code = _unique_code("LOC")

    resp = client.post(
        "/api/v1/stores/location",
        json={
            "location_code": location_code,
            "location_name": f"Location {location_code}",
            "description": "Stores rack",
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["location_code"] == location_code
    assert body["is_active"] is True


def test_stores_cannot_use_inactive_location_for_grn_acceptance():
    token = _get_admin_token()
    inactive_location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Inactive GRN Location",
        is_active=False,
    )
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    item = _add_grn_item(token, grn["id"], batch_number=_traceable_batch_number())

    mtc_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/mtc",
        json={
            "mtc_number": _unique_code("MTC"),
            "chemical_composition_verified": True,
            "mechanical_properties_verified": True,
            "standard_compliance_verified": True,
            "verification_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mtc_resp.status_code == 201

    inspect_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Attempt with inactive location",
            "storage_location_id": inactive_location["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inspect_resp.status_code == 400
    assert "inactive" in inspect_resp.json()["detail"].lower()


def test_stores_rmir_acceptance_blocked_if_location_not_provided():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    batch_number = _traceable_batch_number()
    item = _add_grn_item(token, grn["id"], batch_number=batch_number, accepted="7.000", rejected="3.000")

    mtc_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/mtc",
        json={
            "mtc_number": _unique_code("MTC"),
            "chemical_composition_verified": True,
            "mechanical_properties_verified": True,
            "standard_compliance_verified": True,
            "verification_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mtc_resp.status_code == 201

    inspect_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "No location provided",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inspect_resp.status_code == 400
    assert "storage_location_id is required" in inspect_resp.json()["detail"]


def test_stores_cannot_issue_material_from_inactive_location():
    token = _get_admin_token()
    active_location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Issue Source Location",
        is_active=True,
    )
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    batch_number = _traceable_batch_number()
    item = _add_grn_item(token, grn["id"], batch_number=batch_number, accepted="4.000", rejected="6.000")

    mtc_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/mtc",
        json={
            "mtc_number": _unique_code("MTC"),
            "chemical_composition_verified": True,
            "mechanical_properties_verified": True,
            "standard_compliance_verified": True,
            "verification_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mtc_resp.status_code == 201

    inspect_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Accept into active location",
            "storage_location_id": active_location["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inspect_resp.status_code == 200

    patch_resp = client.patch(
        f"/api/v1/stores/location/{active_location['id']}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_resp.status_code == 200

    issue_resp = client.post(
        "/api/v1/stores/issue",
        json={
            "batch_number": batch_number,
            "storage_location_id": active_location["id"],
            "issue_quantity": "1.000",
            "reference_number": _unique_code("ISSUE"),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issue_resp.status_code == 400
    assert "inactive" in issue_resp.json()["detail"].lower()


def test_stores_cannot_delete_location_if_stock_exists():
    token = _get_admin_token()
    location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Delete Blocked Location",
        is_active=True,
    )
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    item = _add_grn_item(token, grn["id"], batch_number=_traceable_batch_number(), accepted="2.000", rejected="8.000")

    mtc_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/mtc",
        json={
            "mtc_number": _unique_code("MTC"),
            "chemical_composition_verified": True,
            "mechanical_properties_verified": True,
            "standard_compliance_verified": True,
            "verification_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mtc_resp.status_code == 201

    inspect_resp = client.post(
        f"/api/v1/stores/grn/{item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Accept into location",
            "storage_location_id": location["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inspect_resp.status_code == 200

    delete_resp = client.delete(
        f"/api/v1/stores/location/{location['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_resp.status_code == 400
    assert "available stock" in delete_resp.json()["detail"].lower()


def test_stores_can_delete_location_if_no_stock_exists():
    token = _get_admin_token()
    location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Delete Allowed Location",
        is_active=True,
    )

    delete_resp = client.delete(
        f"/api/v1/stores/location/{location['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_resp.status_code == 200
    body = delete_resp.json()
    assert body["id"] == location["id"]
    assert body["is_active"] is False
    assert body["is_deleted"] is True


def test_stores_grn_creation_blocked_if_storage_location_missing():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)

    resp = client.post(
        "/api/v1/stores/grn",
        json={
            "grn_number": _unique_code("GRN"),
            "purchase_order_id": po["id"],
            "supplier_id": supplier["id"],
            "grn_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_stores_grn_creation_blocked_if_location_inactive():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)
    inactive_location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Inactive Receiving",
        is_active=False,
    )

    resp = client.post(
        "/api/v1/stores/grn",
        json={
            "grn_number": _unique_code("GRN"),
            "purchase_order_id": po["id"],
            "supplier_id": supplier["id"],
            "storage_location_id": inactive_location["id"],
            "grn_date": date.today().isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


def test_stores_grn_sets_received_traceability_fields():
    token = _get_admin_token()
    admin_user_id = _get_admin_user_id()
    supplier, po = _create_issued_po(token)
    location = _create_location(
        token,
        location_code=_unique_code("LOC"),
        location_name="Traceability Receiving",
        is_active=True,
    )

    grn = _create_grn(token, po["id"], supplier["id"], storage_location_id=location["id"])
    assert grn["received_by"] == admin_user_id
    assert grn["received_datetime"]
    parsed_dt = datetime.fromisoformat(grn["received_datetime"].replace("Z", "+00:00"))
    assert parsed_dt is not None


def test_stores_invalid_batch_format_rejected():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])

    resp = client.post(
        f"/api/v1/stores/grn/{grn['id']}/item",
        json={
            "item_code": "RM-AL-001",
            "description": "Raw material",
            "heat_number": "HT-002",
            "batch_number": "BATCH-INVALID",
            "received_quantity": "10.000",
            "accepted_quantity": "8.000",
            "rejected_quantity": "2.000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Batch number must follow format" in resp.json()["detail"]


def test_stores_valid_batch_format_accepted():
    token = _get_admin_token()
    supplier, po = _create_issued_po(token)
    grn = _create_grn(token, po["id"], supplier["id"])
    valid_batch = _traceable_batch_number()

    resp = client.post(
        f"/api/v1/stores/grn/{grn['id']}/item",
        json={
            "item_code": "RM-AL-001",
            "description": "Raw material",
            "heat_number": "HT-002",
            "batch_number": valid_batch,
            "received_quantity": "10.000",
            "accepted_quantity": "8.000",
            "rejected_quantity": "2.000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
