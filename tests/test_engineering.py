import random
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.modules.engineering.models import RouteCard
from app.modules.sales.models import (
    ContractReview,
    ContractReviewStatus,
    Customer,
    CustomerPOReview,
    CustomerPOReviewStatus,
    Enquiry,
    EnquiryStatus,
    Quotation,
    QuotationStatus,
    SalesOrder,
    SalesOrderStatus,
)
from app.services.engineering_service import (
    EngineeringBusinessRuleError,
    validate_route_card_for_production,
)

client = TestClient(app)


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


def _seed_sales_order() -> int:
    db = SessionLocal()
    try:
        code = int(uuid4().hex[:8], 16)

        customer = Customer(
            customer_code=f"CUST{code}",
            name=f"Customer {code}",
            email=f"customer{code}@example.com",
            is_active=True,
        )
        db.add(customer)
        db.flush()

        enquiry = Enquiry(
            enquiry_number=f"ENQ{code}",
            customer_id=customer.id,
            enquiry_date=date.today(),
            currency="INR",
            status=EnquiryStatus.DRAFT,
        )
        db.add(enquiry)
        db.flush()

        contract_review = ContractReview(
            document_number=f"CR-{date.today().year}-{code:04d}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            enquiry_id=enquiry.id,
            status=ContractReviewStatus.APPROVED,
            scope_clarity_ok=True,
            capability_ok=True,
            capacity_ok=True,
            delivery_commitment_ok=True,
            quality_requirements_ok=True,
        )
        db.add(contract_review)
        db.flush()

        quotation = Quotation(
            document_number=f"QT-{date.today().year}-{code:04d}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            quotation_number=f"QTN{code}",
            enquiry_id=enquiry.id,
            contract_review_id=contract_review.id,
            customer_id=customer.id,
            issue_date=date.today(),
            valid_until=date.today(),
            currency="INR",
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("18.00"),
            total_amount=Decimal("118.00"),
            status=QuotationStatus.DRAFT,
        )
        db.add(quotation)
        db.flush()

        po_review = CustomerPOReview(
            document_number=f"POA-{date.today().year}-{code:04d}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            quotation_id=quotation.id,
            customer_po_number=f"PO{code}",
            customer_po_date=date.today(),
            accepted=True,
            status=CustomerPOReviewStatus.ACCEPTED,
        )
        db.add(po_review)
        db.flush()

        so = SalesOrder(
            sales_order_number=f"SO{code}",
            customer_id=customer.id,
            enquiry_id=enquiry.id,
            contract_review_id=contract_review.id,
            quotation_id=quotation.id,
            customer_po_review_id=po_review.id,
            order_date=date.today(),
            currency="INR",
            total_amount=Decimal("118.00"),
            status=SalesOrderStatus.DRAFT,
        )
        db.add(so)
        db.commit()
        db.refresh(so)
        return so.id
    finally:
        db.close()


def _create_route_card_with_document(
    *,
    token: str,
    route_number: str,
    drawing_revision_id: int,
    sales_order_id: int,
    filename: str = "route_card.pdf",
    content: bytes = b"Route card content",
    content_type: str = "application/pdf",
):
    return client.post(
        "/api/v1/engineering/route-card",
        data={
            "route_number": route_number,
            "drawing_revision_id": str(drawing_revision_id),
            "sales_order_id": str(sales_order_id),
        },
        files={"file": (filename, content, content_type)},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_engineering_drawing_uniqueness_and_current_revision_rules():
    token = _get_admin_token()
    suffix = random.randint(100000, 999999)
    drawing_number = f"DRW-T-{suffix}"

    create_draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": drawing_number, "part_name": "Part A", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_draw.status_code == 201
    drawing_id = create_draw.json()["id"]

    dup_draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": drawing_number, "part_name": "Part A", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dup_draw.status_code == 400

    rev_a = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "A", "file_path": "/tmp/a.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev_a.status_code == 201

    rev_b = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "B", "file_path": "/tmp/b.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev_b.status_code == 201
    rev_b_id = rev_b.json()["id"]

    revisions = client.get(
        f"/api/v1/engineering/drawing/{drawing_id}/revisions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revisions.status_code == 200
    current_revisions = [x for x in revisions.json() if x["is_current"] is True]
    assert len(current_revisions) == 1
    assert current_revisions[0]["id"] == rev_b_id

    delete_current = client.delete(
        f"/api/v1/engineering/drawing/{drawing_id}/revision/{rev_b_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_current.status_code == 400


def test_engineering_route_card_release_and_post_release_guards():
    token = _get_admin_token()
    sales_order_id = _seed_sales_order()
    suffix = random.randint(100000, 999999)

    draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": f"DRW-RC-{suffix}", "part_name": "Route Part", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draw.status_code == 201
    drawing_id = draw.json()["id"]

    rev = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "A", "file_path": "/tmp/ra.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev.status_code == 201
    revision_id = rev.json()["id"]

    route = _create_route_card_with_document(
        token=token,
        route_number=f"RC-{suffix}",
        drawing_revision_id=revision_id,
        sales_order_id=sales_order_id,
        filename="route_card_release.pdf",
        content=b"Route card release content",
    )
    assert route.status_code == 201
    route_card_id = route.json()["id"]

    release_no_ops = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/release",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert release_no_ops.status_code == 400

    op = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/operation",
        json={
            "operation_number": 10,
            "operation_name": "Cutting",
            "work_center": "WC-1",
            "sequence_order": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert op.status_code == 201
    op_id = op.json()["id"]

    dup_no = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/operation",
        json={
            "operation_number": 10,
            "operation_name": "Drilling",
            "work_center": "WC-2",
            "sequence_order": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dup_no.status_code == 400

    dup_seq = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/operation",
        json={
            "operation_number": 20,
            "operation_name": "Drilling",
            "work_center": "WC-2",
            "sequence_order": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dup_seq.status_code == 400

    release_ok = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/release",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert release_ok.status_code == 200

    edit_after_release = client.patch(
        f"/api/v1/engineering/route-card/{route_card_id}",
        json={"route_number": f"RC-NEW-{suffix}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert edit_after_release.status_code == 400

    add_after_release = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/operation",
        json={
            "operation_number": 30,
            "operation_name": "Inspection",
            "work_center": "WC-3",
            "sequence_order": 3,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add_after_release.status_code == 400

    delete_op_after_release = client.delete(
        f"/api/v1/engineering/route-card/{route_card_id}/operation/{op_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_op_after_release.status_code == 400

    delete_route_after_release = client.delete(
        f"/api/v1/engineering/route-card/{route_card_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_route_after_release.status_code == 400

    obsolete = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/obsolete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert obsolete.status_code == 200
    assert obsolete.json()["status"] == "obsolete"


def test_engineering_soft_delete_and_list_filters_pagination():
    token = _get_admin_token()
    sales_order_id = _seed_sales_order()
    suffix = random.randint(100000, 999999)

    draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": f"DRW-L-{suffix}", "part_name": "List Part", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draw.status_code == 201
    drawing_id = draw.json()["id"]

    rev = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "A", "file_path": "/tmp/la.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev.status_code == 201
    revision_id = rev.json()["id"]

    route = _create_route_card_with_document(
        token=token,
        route_number=f"RCL-{suffix}",
        drawing_revision_id=revision_id,
        sales_order_id=sales_order_id,
        filename="route_card_list.pdf",
    )
    assert route.status_code == 201
    route_card_id = route.json()["id"]

    list_before = client.get(
        "/api/v1/engineering/route-card",
        params={"status": "draft", "skip": 0, "limit": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_before.status_code == 200
    assert len(list_before.json()) <= 1

    list_by_search = client.get(
        "/api/v1/engineering/route-card",
        params={"q": f"RCL-{suffix}", "skip": 0, "limit": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_by_search.status_code == 200
    assert any(item["route_number"] == f"RCL-{suffix}" for item in list_by_search.json())

    delete_route = client.delete(
        f"/api/v1/engineering/route-card/{route_card_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_route.status_code == 204

    list_after = client.get(
        "/api/v1/engineering/route-card",
        params={"skip": 0, "limit": 200},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_after.status_code == 200
    ids = [x["id"] for x in list_after.json()]
    assert route_card_id not in ids


def test_engineering_route_card_rejects_non_current_revision():
    token = _get_admin_token()
    sales_order_id = _seed_sales_order()
    suffix = random.randint(100000, 999999)

    draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": f"DRW-NC-{suffix}", "part_name": "NC Part", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draw.status_code == 201
    drawing_id = draw.json()["id"]

    rev_a = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "A", "file_path": "/tmp/nc-a.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev_a.status_code == 201
    rev_a_id = rev_a.json()["id"]

    rev_b = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "B", "file_path": "/tmp/nc-b.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev_b.status_code == 201

    route = _create_route_card_with_document(
        token=token,
        route_number=f"RC-NC-{suffix}",
        drawing_revision_id=rev_a_id,
        sales_order_id=sales_order_id,
        filename="route_card_non_current.pdf",
    )
    assert route.status_code == 400


def test_engineering_validate_route_card_for_production_rejects_draft():
    token = _get_admin_token()
    sales_order_id = _seed_sales_order()
    suffix = random.randint(100000, 999999)

    draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": f"DRW-VP-{suffix}", "part_name": "VP Part", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draw.status_code == 201
    drawing_id = draw.json()["id"]

    rev = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "A", "file_path": "/tmp/vp-a.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev.status_code == 201
    revision_id = rev.json()["id"]

    route = _create_route_card_with_document(
        token=token,
        route_number=f"RC-VP-{suffix}",
        drawing_revision_id=revision_id,
        sales_order_id=sales_order_id,
        filename="route_card_vp.pdf",
    )
    assert route.status_code == 201
    route_card_id = route.json()["id"]

    db = SessionLocal()
    try:
        route_card = db.scalar(select(RouteCard).where(RouteCard.id == route_card_id))
        assert route_card is not None
        with pytest.raises(EngineeringBusinessRuleError):
            validate_route_card_for_production(route_card)
    finally:
        db.close()


def test_engineering_validate_route_card_for_production_accepts_released():
    token = _get_admin_token()
    sales_order_id = _seed_sales_order()
    suffix = random.randint(100000, 999999)

    draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": f"DRW-VR-{suffix}", "part_name": "VR Part", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draw.status_code == 201
    drawing_id = draw.json()["id"]

    rev = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "A", "file_path": "/tmp/vr-a.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev.status_code == 201
    revision_id = rev.json()["id"]

    route = _create_route_card_with_document(
        token=token,
        route_number=f"RC-VR-{suffix}",
        drawing_revision_id=revision_id,
        sales_order_id=sales_order_id,
        filename="route_card_vr.pdf",
        content=b"Route card prod content",
    )
    assert route.status_code == 201
    route_card_id = route.json()["id"]

    op = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/operation",
        json={
            "operation_number": 10,
            "operation_name": "Cutting",
            "work_center": "WC-1",
            "sequence_order": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert op.status_code == 201

    release_ok = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/release",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert release_ok.status_code == 200

    db = SessionLocal()
    try:
        route_card = db.scalar(select(RouteCard).where(RouteCard.id == route_card_id))
        assert route_card is not None
        validate_route_card_for_production(route_card)
    finally:
        db.close()


def test_engineering_route_card_document_upload_download_and_release_requirement():
    token = _get_admin_token()
    sales_order_id = _seed_sales_order()
    suffix = random.randint(100000, 999999)

    draw = client.post(
        "/api/v1/engineering/drawing",
        json={"drawing_number": f"DRW-DOC-{suffix}", "part_name": "DOC Part", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draw.status_code == 201
    drawing_id = draw.json()["id"]

    rev = client.post(
        f"/api/v1/engineering/drawing/{drawing_id}/revision",
        json={"revision_code": "A", "file_path": "/tmp/doc-a.pdf", "is_current": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev.status_code == 201
    revision_id = rev.json()["id"]

    create_without_file = client.post(
        "/api/v1/engineering/route-card",
        data={
            "route_number": f"RC-DOC-MISSING-{suffix}",
            "drawing_revision_id": str(revision_id),
            "sales_order_id": str(sales_order_id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_without_file.status_code == 422

    route = _create_route_card_with_document(
        token=token,
        route_number=f"RC-DOC-{suffix}",
        drawing_revision_id=revision_id,
        sales_order_id=sales_order_id,
        filename="route_card_doc.pdf",
        content=b"Route card downloadable content",
    )
    assert route.status_code == 201
    route_card_id = route.json()["id"]

    op = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/operation",
        json={
            "operation_number": 10,
            "operation_name": "Milling",
            "work_center": "WC-DOC",
            "sequence_order": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert op.status_code == 201

    download = client.get(
        f"/api/v1/engineering/route-card/{route_card_id}/document/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download.status_code == 200
    assert download.content == b"Route card downloadable content"
    assert "application/pdf" in download.headers.get("content-type", "")

    download_by_traceability = client.get(
        "/api/v1/engineering/route-card/document/download",
        params={"traceability": f"RC-DOC-{suffix}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download_by_traceability.status_code == 200
    assert download_by_traceability.content == b"Route card downloadable content"
    assert "application/pdf" in download_by_traceability.headers.get("content-type", "")

    release_with_doc = client.post(
        f"/api/v1/engineering/route-card/{route_card_id}/release",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert release_with_doc.status_code == 200
