from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.engineering.models import (
    Drawing,
    DrawingRevision,
    RouteCard,
    RouteCardStatus,
    RouteOperation,
)
from app.services.auth_service import add_audit_log


class EngineeringBusinessRuleError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_drawing(
    db: Session,
    *,
    drawing_number: str,
    part_name: str,
    customer_id: int | None = None,
    description: str | None = None,
    is_active: bool = True,
    created_by: int | None = None,
) -> Drawing:
    existing = db.scalar(select(Drawing).where(Drawing.drawing_number == drawing_number))
    if existing:
        raise EngineeringBusinessRuleError("Drawing number already exists")

    drawing = Drawing(
        drawing_number=drawing_number,
        part_name=part_name,
        customer_id=customer_id,
        description=description,
        is_active=is_active,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


def create_route_card(
    db: Session,
    *,
    route_number: str,
    drawing_revision_id: int,
    sales_order_id: int,
    created_by: int | None = None,
) -> RouteCard:
    drawing_revision = db.scalar(
        select(DrawingRevision).where(DrawingRevision.id == drawing_revision_id)
    )
    if not drawing_revision:
        raise EngineeringBusinessRuleError("Drawing revision not found")

    if not drawing_revision.is_current:
        raise EngineeringBusinessRuleError("Drawing revision must be current before route creation")

    route_card = RouteCard(
        route_number=route_number,
        drawing_revision_id=drawing_revision_id,
        sales_order_id=sales_order_id,
        status=RouteCardStatus.DRAFT,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(route_card)
    db.commit()
    db.refresh(route_card)
    return route_card


def add_route_operation(
    db: Session,
    *,
    route_card_id: int,
    operation_number: int | None,
    operation_name: str,
    work_center: str,
    inspection_required: bool = False,
    sequence_order: int,
    created_by: int | None = None,
) -> RouteOperation:
    route_card = db.scalar(select(RouteCard).where(RouteCard.id == route_card_id))
    if not route_card:
        raise EngineeringBusinessRuleError("RouteCard not found")

    if route_card.status == RouteCardStatus.RELEASED:
        raise EngineeringBusinessRuleError("Cannot add operations after RouteCard is Released")

    if operation_number is None:
        max_op = db.scalar(
            select(RouteOperation.operation_number)
            .where(RouteOperation.route_card_id == route_card_id)
            .order_by(RouteOperation.operation_number.desc())
        )
        operation_number = (max_op or 0) + 10

    existing_op = db.scalar(
        select(RouteOperation.id).where(
            RouteOperation.route_card_id == route_card_id,
            RouteOperation.operation_number == operation_number,
        )
    )
    if existing_op:
        raise EngineeringBusinessRuleError("Operation number must be unique per RouteCard")

    existing_seq = db.scalar(
        select(RouteOperation.id).where(
            RouteOperation.route_card_id == route_card_id,
            RouteOperation.sequence_order == sequence_order,
        )
    )
    if existing_seq:
        raise EngineeringBusinessRuleError("Sequence order must be unique per RouteCard")

    operation = RouteOperation(
        route_card_id=route_card_id,
        operation_number=operation_number,
        operation_name=operation_name,
        work_center=work_center,
        inspection_required=inspection_required,
        sequence_order=sequence_order,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(operation)
    db.commit()
    db.refresh(operation)
    return operation


def create_revision(
    db: Session,
    *,
    drawing_id: int,
    revision_code: str,
    revision_date: datetime | None = None,
    file_path: str,
    is_current: bool = False,
    approved_by: int | None = None,
    approved_date: datetime | None = None,
    created_by: int | None = None,
) -> DrawingRevision:
    drawing = db.scalar(select(Drawing).where(Drawing.id == drawing_id))
    if not drawing:
        raise EngineeringBusinessRuleError("Drawing not found")

    revision_date_value = revision_date.date() if isinstance(revision_date, datetime) else revision_date
    if revision_date_value is None:
        revision_date_value = _utc_now().date()

    if is_current:
        previous_current = db.scalars(
            select(DrawingRevision).where(
                DrawingRevision.drawing_id == drawing_id,
                DrawingRevision.is_current.is_(True),
            )
        ).all()
        for revision in previous_current:
            revision.is_current = False
            revision.updated_by = created_by
            db.add(revision)

    revision = DrawingRevision(
        drawing_id=drawing_id,
        revision_code=revision_code,
        revision_date=revision_date_value,
        file_path=file_path,
        is_current=is_current,
        approved_by=approved_by,
        approved_date=approved_date,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)

    add_audit_log(
        db=db,
        user_id=created_by,
        action="DRAWING_REVISION_CREATED",
        table_name="drawing_revisions",
        record_id=revision.id,
        new_value={
            "drawing_id": revision.drawing_id,
            "revision_code": revision.revision_code,
            "is_current": revision.is_current,
        },
    )

    return revision


def release_route_card(
    db: Session,
    *,
    route_card_id: int,
    released_by: int | None = None,
) -> RouteCard:
    route_card = db.scalar(select(RouteCard).where(RouteCard.id == route_card_id))
    if not route_card:
        raise EngineeringBusinessRuleError("RouteCard not found")

    if route_card.status != RouteCardStatus.DRAFT:
        raise EngineeringBusinessRuleError("RouteCard can only be released from Draft status")

    operations_exist = db.scalar(
        select(RouteOperation.id).where(RouteOperation.route_card_id == route_card_id)
    )
    if not operations_exist:
        raise EngineeringBusinessRuleError("RouteCard cannot be released without operations")

    missing_sequence = db.scalar(
        select(RouteOperation.id).where(
            RouteOperation.route_card_id == route_card_id,
            RouteOperation.sequence_order.is_(None),
        )
    )
    if missing_sequence:
        raise EngineeringBusinessRuleError("All operations must have sequence_order before release")

    if not route_card.drawing_revision.is_current:
        raise EngineeringBusinessRuleError("Drawing revision must be current before route release")

    route_card.status = RouteCardStatus.RELEASED
    route_card.released_by = released_by
    route_card.released_date = _utc_now()
    route_card.updated_by = released_by
    db.add(route_card)
    db.commit()
    db.refresh(route_card)

    add_audit_log(
        db=db,
        user_id=released_by,
        action="ROUTE_CARD_RELEASED",
        table_name="route_cards",
        record_id=route_card.id,
        new_value={"status": route_card.status.value},
    )

    return route_card


def mark_route_card_obsolete(
    db: Session,
    *,
    route_card_id: int,
    updated_by: int | None = None,
) -> RouteCard:
    route_card = db.scalar(select(RouteCard).where(RouteCard.id == route_card_id))
    if not route_card:
        raise EngineeringBusinessRuleError("RouteCard not found")

    if route_card.status != RouteCardStatus.RELEASED:
        raise EngineeringBusinessRuleError("RouteCard can only be marked obsolete from Released status")

    route_card.status = RouteCardStatus.OBSOLETE
    route_card.updated_by = updated_by
    db.add(route_card)
    db.commit()
    db.refresh(route_card)

    add_audit_log(
        db=db,
        user_id=updated_by,
        action="ROUTE_CARD_OBSOLETE",
        table_name="route_cards",
        record_id=route_card.id,
        new_value={"status": route_card.status.value},
    )

    return route_card


def validate_route_card_for_production(route_card: RouteCard) -> None:
    if route_card.status != RouteCardStatus.RELEASED:
        raise EngineeringBusinessRuleError("RouteCard must be Released before production")
