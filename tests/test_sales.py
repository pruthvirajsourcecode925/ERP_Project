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
from app.modules.sales.models import (
    ContractReview,
    ContractReviewStatus,
    Customer,
    CustomerPOReview,
    CustomerPOReviewStatus,
    Enquiry,
    EnquiryStatus,
    Quotation,
    QuotationItem,
    QuotationStatus,
)
from app.modules.sales.pdf_generator import QuotationLineItem, QuotationPDFData, generate_quotation_pdf
from app.modules.sales.pdf.po_review_pdf import (
    CustomerPOReviewPDFPayload,
    VerificationChecklistItem as POReviewChecklistItem,
    generate_customer_po_review_pdf,
)

client = TestClient(app)


def _unique_seed_code() -> int:
    return int(uuid4().hex[:8], 16)


def _get_token_for_role(role_name: str) -> str:
    db = SessionLocal()
    try:
        role = db.scalar(select(Role).where(Role.name == role_name))
        assert role is not None

        uid = uuid4().hex[:10]
        username = f"{role_name.lower()}user{uid}"

        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash=get_password_hash("Password@123"),
            role_id=role.id,
            auth_provider="local",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            is_deleted=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return create_access_token(str(user.id))
    finally:
        db.close()


def _seed_sales_records(
    *,
    contract_status: ContractReviewStatus,
    all_checks_true: bool,
    po_accepted: bool,
    seed_code: int | None = None,
) -> tuple[int, int, int, int, int]:
    db = SessionLocal()
    try:
        code = seed_code or _unique_seed_code()

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
            generated_by=None,
            enquiry_id=enquiry.id,
            status=contract_status,
            scope_clarity_ok=all_checks_true,
            capability_ok=all_checks_true,
            capacity_ok=all_checks_true,
            delivery_commitment_ok=all_checks_true,
            quality_requirements_ok=all_checks_true,
        )
        db.add(contract_review)
        db.flush()

        quotation = Quotation(
            document_number=f"QT-{date.today().year}-{code:04d}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            generated_by=None,
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
            generated_by=None,
            quotation_id=quotation.id,
            customer_po_number=f"PO{code}",
            customer_po_date=date.today(),
            accepted=po_accepted,
            status=CustomerPOReviewStatus.ACCEPTED if po_accepted else CustomerPOReviewStatus.PENDING,
        )
        db.add(po_review)
        db.commit()

        return customer.id, enquiry.id, contract_review.id, quotation.id, po_review.id
    finally:
        db.close()


def _seed_sales_upto_quotation(
    *,
    contract_status: ContractReviewStatus,
    all_checks_true: bool,
    seed_code: int | None = None,
) -> tuple[int, int, int, int]:
    db = SessionLocal()
    try:
        code = seed_code or _unique_seed_code()

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
            generated_by=None,
            enquiry_id=enquiry.id,
            status=contract_status,
            scope_clarity_ok=all_checks_true,
            capability_ok=all_checks_true,
            capacity_ok=all_checks_true,
            delivery_commitment_ok=all_checks_true,
            quality_requirements_ok=all_checks_true,
        )
        db.add(contract_review)
        db.flush()

        quotation = Quotation(
            document_number=f"QT-{date.today().year}-{code:04d}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            generated_by=None,
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
        db.commit()

        return customer.id, enquiry.id, contract_review.id, quotation.id
    finally:
        db.close()


def test_cannot_create_quotation_if_feasibility_checkbox_false():
    token = _get_token_for_role("Sales")
    customer_id, enquiry_id, contract_review_id, _, _ = _seed_sales_records(
        contract_status=ContractReviewStatus.PENDING,
        all_checks_true=False,
        po_accepted=False,
    )

    response = client.post(
        "/api/v1/sales/quotation",
        json={
            "quotation_number": f"QTNX{random.randint(10000, 99999)}",
            "enquiry_id": enquiry_id,
            "contract_review_id": contract_review_id,
            "customer_id": customer_id,
            "issue_date": str(date.today()),
            "valid_until": str(date.today()),
            "currency": "INR",
            "subtotal": "100.00",
            "tax_amount": "18.00",
            "total_amount": "118.00",
            "status": "draft",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "quotation cannot be generated due to incomplete contract review" in detail.lower()
    assert "the following feasibility items are not approved" in detail.lower()
    assert "• Drawing availability" in detail


def test_cannot_create_sales_order_without_approved_contract_review():
    token = _get_token_for_role("Sales")
    customer_id, enquiry_id, contract_review_id, quotation_id, po_review_id = _seed_sales_records(
        contract_status=ContractReviewStatus.PENDING,
        all_checks_true=True,
        po_accepted=True,
    )

    response = client.post(
        "/api/v1/sales/sales-order",
        json={
            "sales_order_number": f"SO{random.randint(10000, 99999)}",
            "customer_id": customer_id,
            "enquiry_id": enquiry_id,
            "contract_review_id": contract_review_id,
            "quotation_id": quotation_id,
            "customer_po_review_id": po_review_id,
            "order_date": str(date.today()),
            "currency": "INR",
            "total_amount": "118.00",
            "status": "draft",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "approved" in response.json()["detail"].lower()


def test_cannot_create_sales_order_without_accepted_po():
    token = _get_token_for_role("Sales")
    customer_id, enquiry_id, contract_review_id, quotation_id, po_review_id = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=False,
    )

    response = client.post(
        "/api/v1/sales/sales-order",
        json={
            "sales_order_number": f"SO{random.randint(10000, 99999)}",
            "customer_id": customer_id,
            "enquiry_id": enquiry_id,
            "contract_review_id": contract_review_id,
            "quotation_id": quotation_id,
            "customer_po_review_id": po_review_id,
            "order_date": str(date.today()),
            "currency": "INR",
            "total_amount": "118.00",
            "status": "draft",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "accepted" in response.json()["detail"].lower()


def test_quotation_pdf_generation_success():
    line_items = [
        QuotationLineItem(
            line_no=1,
            item_code="ITEM-001",
            description="Aerospace Bracket",
            quantity=Decimal("10"),
            uom="Nos",
            unit_price=Decimal("125.50"),
        )
    ]

    result = generate_quotation_pdf(
        QuotationPDFData(
            quotation_number=f"QPDF{random.randint(1000, 9999)}",
            quotation_date=date.today(),
            company_info={
                "name": "AS9100D ERP Manufacturing Pvt Ltd",
                "address_line_1": "Industrial Area",
                "city_state_zip": "Pune, MH 411001",
                "country": "India",
                "phone": "+91-00000-00000",
                "email": "sales@as9100d-erp.local",
                "gstin": "27ABCDE1234F1Z5",
            },
            customer_info={
                "name": "Test Customer",
                "address_line_1": "Customer Street",
                "city_state_zip": "Bengaluru, KA",
                "country": "India",
                "contact_person": "QA User",
                "email": "qa@example.com",
            },
            enquiry_reference="ENQ-REF-001",
            line_items=line_items,
            delivery_terms="4 weeks from PO",
            payment_terms="30 days",
            gst_details="GST extra",
            validity="30 days",
            fai_required=True,
            coc_required=True,
            traceability_required=True,
            terms_and_conditions=["All quality requirements as per contract review."],
        )
    )

    file_path = Path(result["file_path"])
    assert file_path.exists()
    assert file_path.suffix.lower() == ".pdf"


def test_customer_po_review_pdf_generation_success():
    payload = CustomerPOReviewPDFPayload(
        po_review_no=f"POA-{random.randint(1000, 9999)}",
        review_date=date.today(),
        ref_no="REF-PO-001",
        mode="Enq. By Mail",
        customer_info={
            "name": "Test Customer",
            "address_line_1": "Customer Street",
            "address_line_2": "Industrial Area",
            "city_state_zip": "Bengaluru, KA",
            "country": "India",
            "contact_person": "QA User",
            "email": "qa@example.com",
        },
        po_info={
            "po_number": "PO-001",
            "po_date": date.today().isoformat(),
            "quotation_ref": "QT-001",
            "enquiry_ref": "ENQ-001",
            "currency": "INR",
            "po_value": "1000.00",
        },
        verification_items=[
            POReviewChecklistItem(
                sr_no=1,
                item="PO references valid quotation",
                status="OK",
                remarks="Matched with QT-001",
            )
        ],
        acceptance_declaration=(
            "As per AS9100D requirements, this Customer PO has been reviewed and accepted."
        ),
        approved_by="QA Approver",
        approval_date=date.today().isoformat(),
    )

    result = generate_customer_po_review_pdf(payload)

    file_path = Path(result["file_path"])
    assert file_path.exists()
    assert file_path.suffix.lower() == ".pdf"


def test_role_restriction_enforcement():
    token = _get_token_for_role("Auditor")

    response = client.post(
        "/api/v1/sales/enquiry",
        json={
            "enquiry_number": f"ENQ{random.randint(10000, 99999)}",
            "customer_id": 1,
            "enquiry_date": str(date.today()),
            "currency": "INR",
            "status": "draft",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_customer_po_review_pdf_download_success():
    token = _get_token_for_role("Sales")
    _, _, _, _, po_review_id = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
    )

    response = client.get(
        f"/api/v1/sales/customer-po-review/{po_review_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/pdf")
    assert response.content[:4] == b"%PDF"


def test_cannot_create_customer_po_review_if_feasibility_checkbox_false():
    token = _get_token_for_role("Sales")
    _, _, _, quotation_id = _seed_sales_upto_quotation(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=False,
    )

    response = client.post(
        "/api/v1/sales/customer-po-review",
        json={
            "quotation_id": quotation_id,
            "customer_po_number": f"PO{random.randint(10000, 99999)}",
            "customer_po_date": str(date.today()),
            "accepted": False,
            "status": "pending",
            "deviation_notes": "Pending contract closure",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "quotation cannot be generated due to incomplete contract review" in detail.lower()
    assert "the following feasibility items are not approved" in detail.lower()
    assert "• Drawing availability" in detail


def test_customer_po_review_pdf_download_blocked_if_feasibility_checkbox_false():
    token = _get_token_for_role("Sales")
    _, _, _, _, po_review_id = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=False,
        po_accepted=True,
    )

    response = client.get(
        f"/api/v1/sales/customer-po-review/{po_review_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "quotation cannot be generated due to incomplete contract review" in detail.lower()
    assert "the following feasibility items are not approved" in detail.lower()
    assert "• Drawing availability" in detail


def test_admin_can_update_quotation_terms():
    token = _get_token_for_role("Admin")
    payload = {"terms": ["Admin term A", "Admin term B"]}

    response = client.put(
        "/api/v1/sales/quotation-terms",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["terms"] == payload["terms"]

    get_response = client.get(
        "/api/v1/sales/quotation-terms",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert get_response.status_code == 200
    assert get_response.json()["terms"] == payload["terms"]


def test_sales_cannot_update_quotation_terms():
    token = _get_token_for_role("Sales")
    payload = {"terms": ["Unauthorized term"]}

    response = client.put(
        "/api/v1/sales/quotation-terms",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_quotation_pdf_download_success():
    token = _get_token_for_role("Sales")
    _, _, _, quotation_id, _ = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
    )

    response = client.get(
        f"/api/v1/sales/quotation/{quotation_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/pdf")
    assert response.content[:4] == b"%PDF"


def test_quotation_pdf_download_blocked_if_feasibility_checkbox_false():
    token = _get_token_for_role("Sales")
    _, _, _, quotation_id, _ = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=False,
        po_accepted=True,
    )

    response = client.get(
        f"/api/v1/sales/quotation/{quotation_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "quotation cannot be generated due to incomplete contract review" in detail.lower()
    assert "the following feasibility items are not approved" in detail.lower()
    assert "• Drawing availability" in detail


def test_quotation_pdf_download_lists_only_failed_feasibility_items():
    token = _get_token_for_role("Sales")
    _, _, contract_review_id, quotation_id, _ = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
    )

    db = SessionLocal()
    try:
        review = db.scalar(select(ContractReview).where(ContractReview.id == contract_review_id))
        assert review is not None
        review.scope_clarity_ok = False
        review.delivery_commitment_ok = False
        review.capability_ok = True
        review.capacity_ok = True
        review.quality_requirements_ok = True
        db.commit()
    finally:
        db.close()

    response = client.get(
        f"/api/v1/sales/quotation/{quotation_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "• Drawing availability" in detail
    assert "• Delivery feasibility" in detail
    assert "• Special processes" not in detail
    assert "• Capacity & machine suitability" not in detail
    assert "• Quality requirements (FAI, COC, Traceability)" not in detail


def test_list_enquiries_supports_search_and_pagination():
    token = _get_token_for_role("Sales")
    base = _unique_seed_code()
    _seed_sales_upto_quotation(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        seed_code=base,
    )
    _seed_sales_upto_quotation(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        seed_code=base + 1,
    )
    _seed_sales_upto_quotation(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        seed_code=base + 2,
    )

    search_response = client.get(
        "/api/v1/sales/enquiry",
        params={"q": f"ENQ{base + 1}", "skip": 0, "limit": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert any(item["enquiry_number"] == f"ENQ{base + 1}" for item in search_data)

    page_response = client.get(
        "/api/v1/sales/enquiry",
        params={"skip": 0, "limit": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_response.status_code == 200
    assert len(page_response.json()) <= 2


def test_list_quotations_supports_search_and_pagination():
    token = _get_token_for_role("Sales")
    base = _unique_seed_code()
    _seed_sales_upto_quotation(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        seed_code=base,
    )
    _seed_sales_upto_quotation(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        seed_code=base + 1,
    )
    _seed_sales_upto_quotation(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        seed_code=base + 2,
    )

    search_response = client.get(
        "/api/v1/sales/quotation",
        params={"q": f"QTN{base + 1}", "skip": 0, "limit": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert any(item["quotation_number"] == f"QTN{base + 1}" for item in search_data)

    page_response = client.get(
        "/api/v1/sales/quotation",
        params={"skip": 0, "limit": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_response.status_code == 200
    assert len(page_response.json()) <= 2


def test_list_customer_po_reviews_supports_search_and_pagination():
    token = _get_token_for_role("Sales")
    base = _unique_seed_code()
    _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
        seed_code=base,
    )
    _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
        seed_code=base + 1,
    )
    _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
        seed_code=base + 2,
    )

    search_response = client.get(
        "/api/v1/sales/customer-po-review",
        params={"q": f"PO{base + 1}", "skip": 0, "limit": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert any(item["customer_po_number"] == f"PO{base + 1}" for item in search_data)

    page_response = client.get(
        "/api/v1/sales/customer-po-review",
        params={"skip": 0, "limit": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_response.status_code == 200
    assert len(page_response.json()) <= 2


def test_list_sales_orders_supports_search_and_pagination():
    token = _get_token_for_role("Sales")
    base = _unique_seed_code()

    customer_id, enquiry_id, contract_review_id, quotation_id, po_review_id = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
        seed_code=base,
    )
    create_one = client.post(
        "/api/v1/sales/sales-order",
        json={
            "sales_order_number": f"SO{base}",
            "customer_id": customer_id,
            "enquiry_id": enquiry_id,
            "contract_review_id": contract_review_id,
            "quotation_id": quotation_id,
            "customer_po_review_id": po_review_id,
            "order_date": str(date.today()),
            "currency": "INR",
            "total_amount": "118.00",
            "status": "draft",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_one.status_code == 201

    customer_id, enquiry_id, contract_review_id, quotation_id, po_review_id = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
        seed_code=base + 1,
    )
    create_two = client.post(
        "/api/v1/sales/sales-order",
        json={
            "sales_order_number": f"SO{base + 1}",
            "customer_id": customer_id,
            "enquiry_id": enquiry_id,
            "contract_review_id": contract_review_id,
            "quotation_id": quotation_id,
            "customer_po_review_id": po_review_id,
            "order_date": str(date.today()),
            "currency": "INR",
            "total_amount": "118.00",
            "status": "draft",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_two.status_code == 201

    customer_id, enquiry_id, contract_review_id, quotation_id, po_review_id = _seed_sales_records(
        contract_status=ContractReviewStatus.APPROVED,
        all_checks_true=True,
        po_accepted=True,
        seed_code=base + 2,
    )
    create_three = client.post(
        "/api/v1/sales/sales-order",
        json={
            "sales_order_number": f"SO{base + 2}",
            "customer_id": customer_id,
            "enquiry_id": enquiry_id,
            "contract_review_id": contract_review_id,
            "quotation_id": quotation_id,
            "customer_po_review_id": po_review_id,
            "order_date": str(date.today()),
            "currency": "INR",
            "total_amount": "118.00",
            "status": "draft",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_three.status_code == 201

    search_response = client.get(
        "/api/v1/sales/sales-order",
        params={"q": f"SO{base + 1}", "skip": 0, "limit": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert any(item["sales_order_number"] == f"SO{base + 1}" for item in search_data)

    page_response = client.get(
        "/api/v1/sales/sales-order",
        params={"skip": 0, "limit": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_response.status_code == 200
    assert len(page_response.json()) <= 2
