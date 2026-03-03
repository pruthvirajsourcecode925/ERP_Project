from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.engineering.models import (
    Drawing,
    DrawingRevision,
    EngineeringReleaseStatus,
    RouteCard,
    RouteCardStatus,
    RouteOperation,
)
from app.services.auth_service import add_audit_log
from app.services.engineering_service import (
    EngineeringBusinessRuleError,
    add_route_operation,
    create_drawing,
    create_revision,
    create_route_card,
    mark_route_card_obsolete,
    release_route_card,
)

router = APIRouter(prefix="/engineering", tags=["engineering"])


class DrawingCreate(BaseModel):
    drawing_number: str
    part_name: str
    customer_id: int | None = None
    description: str | None = None
    is_active: bool = True


class DrawingOut(BaseModel):
    id: int
    drawing_number: str
    part_name: str
    customer_id: int | None
    description: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DrawingUpdate(BaseModel):
    part_name: str | None = None
    customer_id: int | None = None
    description: str | None = None
    is_active: bool | None = None


class DrawingRevisionCreate(BaseModel):
    revision_code: str
    revision_date: date | None = None
    file_path: str
    is_current: bool = False
    approved_by: int | None = None
    approved_date: datetime | None = None


class DrawingRevisionOut(BaseModel):
    id: int
    drawing_id: int
    revision_code: str
    revision_date: date
    file_path: str
    is_current: bool
    approved_by: int | None
    approved_date: datetime | None

    model_config = {"from_attributes": True}


class DrawingRevisionUpdate(BaseModel):
    revision_code: str | None = None
    revision_date: date | None = None
    file_path: str | None = None
    approved_by: int | None = None
    approved_date: datetime | None = None


class RouteCardCreate(BaseModel):
    route_number: str
    drawing_revision_id: int
    sales_order_id: int


class RouteCardOut(BaseModel):
    id: int
    route_number: str
    drawing_revision_id: int
    sales_order_id: int
    status: RouteCardStatus
    released_by: int | None
    released_date: datetime | None

    model_config = {"from_attributes": True}


class RouteCardUpdate(BaseModel):
    route_number: str | None = None
    drawing_revision_id: int | None = None
    sales_order_id: int | None = None


class RouteOperationCreate(BaseModel):
    operation_number: int | None = None
    operation_name: str
    work_center: str
    inspection_required: bool = False
    sequence_order: int


class RouteOperationOut(BaseModel):
    id: int
    route_card_id: int
    operation_number: int
    operation_name: str
    work_center: str
    inspection_required: bool
    sequence_order: int

    model_config = {"from_attributes": True}


class RouteOperationUpdate(BaseModel):
    operation_number: int | None = None
    operation_name: str | None = None
    work_center: str | None = None
    inspection_required: bool | None = None
    sequence_order: int | None = None


class EngineeringReleaseOut(BaseModel):
    route_card_id: int
    status: RouteCardStatus
    released_by: int | None
    released_date: datetime | None
    release_status: EngineeringReleaseStatus = EngineeringReleaseStatus.APPROVED

    model_config = {"from_attributes": True}


@router.post("/drawing", response_model=DrawingOut, status_code=status.HTTP_201_CREATED)
def create_drawing_endpoint(
    payload: DrawingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    try:
        drawing = create_drawing(
            db,
            drawing_number=payload.drawing_number,
            part_name=payload.part_name,
            customer_id=payload.customer_id,
            description=payload.description,
            is_active=payload.is_active,
            created_by=current_user.id,
        )
    except EngineeringBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="DRAWING_CREATED",
        table_name="drawings",
        record_id=drawing.id,
        new_value={"drawing_number": drawing.drawing_number, "part_name": drawing.part_name},
    )

    return drawing


@router.patch("/drawing/{drawing_id}", response_model=DrawingOut)
def update_drawing_endpoint(
    drawing_id: int,
    payload: DrawingUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    drawing = db.scalar(select(Drawing).where(Drawing.id == drawing_id, Drawing.is_deleted.is_(False)))
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(drawing, field, value)
    drawing.updated_by = current_user.id
    db.add(drawing)
    db.commit()
    db.refresh(drawing)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="DRAWING_UPDATED",
        table_name="drawings",
        record_id=drawing.id,
        new_value=data,
    )

    return drawing


@router.post(
    "/drawing/{drawing_id}/revision",
    response_model=DrawingRevisionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_drawing_revision_endpoint(
    drawing_id: int,
    payload: DrawingRevisionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    try:
        revision = create_revision(
            db,
            drawing_id=drawing_id,
            revision_code=payload.revision_code,
            revision_date=payload.revision_date,
            file_path=payload.file_path,
            is_current=payload.is_current,
            approved_by=payload.approved_by,
            approved_date=payload.approved_date,
            created_by=current_user.id,
        )
    except EngineeringBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return revision


@router.patch("/drawing/{drawing_id}/revision/{revision_id}", response_model=DrawingRevisionOut)
def update_drawing_revision_endpoint(
    drawing_id: int,
    revision_id: int,
    payload: DrawingRevisionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    revision = db.scalar(
        select(DrawingRevision).where(
            DrawingRevision.id == revision_id,
            DrawingRevision.drawing_id == drawing_id,
            DrawingRevision.is_deleted.is_(False),
        )
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Drawing revision not found")

    if revision.is_current:
        raise HTTPException(status_code=400, detail="Current revision cannot be edited")

    if revision.approved_by is not None or revision.approved_date is not None:
        raise HTTPException(status_code=400, detail="Approved revision cannot be edited")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(revision, field, value)
    revision.updated_by = current_user.id
    db.add(revision)
    db.commit()
    db.refresh(revision)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="DRAWING_REVISION_UPDATED",
        table_name="drawing_revisions",
        record_id=revision.id,
        new_value=data,
    )

    return revision


@router.post("/route-card", response_model=RouteCardOut, status_code=status.HTTP_201_CREATED)
def create_route_card_endpoint(
    payload: RouteCardCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    try:
        route_card = create_route_card(
            db,
            route_number=payload.route_number,
            drawing_revision_id=payload.drawing_revision_id,
            sales_order_id=payload.sales_order_id,
            created_by=current_user.id,
        )
    except EngineeringBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROUTE_CARD_CREATED",
        table_name="route_cards",
        record_id=route_card.id,
        new_value={"route_number": route_card.route_number, "status": route_card.status.value},
    )

    return route_card


@router.patch("/route-card/{route_card_id}", response_model=RouteCardOut)
def update_route_card_endpoint(
    route_card_id: int,
    payload: RouteCardUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    route_card = db.scalar(
        select(RouteCard).where(RouteCard.id == route_card_id, RouteCard.is_deleted.is_(False))
    )
    if not route_card:
        raise HTTPException(status_code=404, detail="RouteCard not found")

    if route_card.status != RouteCardStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Released RouteCard cannot be edited")

    data = payload.model_dump(exclude_unset=True)
    if "drawing_revision_id" in data:
        revision = db.scalar(select(DrawingRevision).where(DrawingRevision.id == data["drawing_revision_id"]))
        if not revision or not revision.is_current:
            raise HTTPException(status_code=400, detail="Drawing revision must be current for update")

    for field, value in data.items():
        setattr(route_card, field, value)
    route_card.updated_by = current_user.id
    db.add(route_card)
    db.commit()
    db.refresh(route_card)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROUTE_CARD_UPDATED",
        table_name="route_cards",
        record_id=route_card.id,
        new_value=data,
    )

    return route_card


@router.post(
    "/route-card/{route_card_id}/operation",
    response_model=RouteOperationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_route_operation_endpoint(
    route_card_id: int,
    payload: RouteOperationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    try:
        operation = add_route_operation(
            db,
            route_card_id=route_card_id,
            operation_number=payload.operation_number,
            operation_name=payload.operation_name,
            work_center=payload.work_center,
            inspection_required=payload.inspection_required,
            sequence_order=payload.sequence_order,
            created_by=current_user.id,
        )
    except EngineeringBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROUTE_OPERATION_CREATED",
        table_name="route_operations",
        record_id=operation.id,
        new_value={
            "route_card_id": operation.route_card_id,
            "operation_number": operation.operation_number,
            "sequence_order": operation.sequence_order,
        },
    )

    return operation


@router.patch(
    "/route-card/{route_card_id}/operation/{operation_id}",
    response_model=RouteOperationOut,
)
def update_route_operation_endpoint(
    route_card_id: int,
    operation_id: int,
    payload: RouteOperationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    operation = db.scalar(
        select(RouteOperation).where(
            RouteOperation.id == operation_id,
            RouteOperation.route_card_id == route_card_id,
            RouteOperation.is_deleted.is_(False),
        )
    )
    if not operation:
        raise HTTPException(status_code=404, detail="RouteOperation not found")

    route_card = db.scalar(select(RouteCard).where(RouteCard.id == route_card_id))
    if not route_card:
        raise HTTPException(status_code=404, detail="RouteCard not found")
    if route_card.status != RouteCardStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Released RouteCard cannot be edited")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(operation, field, value)
    operation.updated_by = current_user.id
    db.add(operation)
    db.commit()
    db.refresh(operation)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROUTE_OPERATION_UPDATED",
        table_name="route_operations",
        record_id=operation.id,
        new_value=data,
    )

    return operation


@router.post("/route-card/{route_card_id}/release", response_model=EngineeringReleaseOut)
def release_route_card_endpoint(
    route_card_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    try:
        route_card = release_route_card(
            db,
            route_card_id=route_card_id,
            released_by=current_user.id,
        )
    except EngineeringBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return EngineeringReleaseOut(
        route_card_id=route_card.id,
        status=route_card.status,
        released_by=route_card.released_by,
        released_date=route_card.released_date,
        release_status=EngineeringReleaseStatus.APPROVED,
    )


@router.post("/route-card/{route_card_id}/obsolete", response_model=RouteCardOut)
def obsolete_route_card_endpoint(
    route_card_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    try:
        route_card = mark_route_card_obsolete(
            db,
            route_card_id=route_card_id,
            updated_by=current_user.id,
        )
    except EngineeringBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return route_card


@router.get("/drawing", response_model=list[DrawingOut])
def list_drawings(
    drawing_number: str | None = Query(None),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    stmt = select(Drawing).where(Drawing.is_deleted.is_(False))
    if drawing_number:
        stmt = stmt.where(Drawing.drawing_number.ilike(f"%{drawing_number}%"))
    if is_active is not None:
        stmt = stmt.where(Drawing.is_active.is_(is_active))

    drawings = db.scalars(stmt.order_by(Drawing.id.desc()).offset(skip).limit(limit)).all()
    return drawings


@router.get("/route-card", response_model=list[RouteCardOut])
def list_route_cards(
    status: RouteCardStatus | None = Query(None),
    drawing_id: int | None = Query(None),
    sales_order_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    stmt = select(RouteCard).where(RouteCard.is_deleted.is_(False))
    if status is not None:
        stmt = stmt.where(RouteCard.status == status)
    if drawing_id is not None:
        stmt = stmt.join(DrawingRevision).where(DrawingRevision.drawing_id == drawing_id)
    if sales_order_id is not None:
        stmt = stmt.where(RouteCard.sales_order_id == sales_order_id)

    route_cards = db.scalars(stmt.order_by(RouteCard.id.desc()).offset(skip).limit(limit)).all()
    return route_cards


@router.get("/drawing/{drawing_id}/revisions", response_model=list[DrawingRevisionOut])
def list_drawing_revisions(
    drawing_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    revisions = db.scalars(
        select(DrawingRevision)
        .where(
            DrawingRevision.drawing_id == drawing_id,
            DrawingRevision.is_deleted.is_(False),
        )
        .order_by(DrawingRevision.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return revisions


@router.delete("/drawing/{drawing_id}/revision/{revision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_drawing_revision(
    drawing_id: int,
    revision_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    revision = db.scalar(
        select(DrawingRevision).where(
            DrawingRevision.id == revision_id,
            DrawingRevision.drawing_id == drawing_id,
            DrawingRevision.is_deleted.is_(False),
        )
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Drawing revision not found")

    if revision.is_current:
        raise HTTPException(status_code=400, detail="Current revision cannot be deleted")

    if revision.approved_by is not None or revision.approved_date is not None:
        raise HTTPException(status_code=400, detail="Approved revision cannot be deleted")

    revision.is_deleted = True
    revision.updated_by = current_user.id
    db.add(revision)
    db.commit()

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="DRAWING_REVISION_DELETED",
        table_name="drawing_revisions",
        record_id=revision.id,
    )

    return None


@router.delete("/route-card/{route_card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route_card(
    route_card_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    route_card = db.scalar(
        select(RouteCard).where(RouteCard.id == route_card_id, RouteCard.is_deleted.is_(False))
    )
    if not route_card:
        raise HTTPException(status_code=404, detail="RouteCard not found")

    if route_card.status != RouteCardStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Released RouteCard cannot be deleted")

    route_card.is_deleted = True
    route_card.updated_by = current_user.id
    db.add(route_card)
    db.commit()

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROUTE_CARD_DELETED",
        table_name="route_cards",
        record_id=route_card.id,
    )

    return None


@router.delete(
    "/route-card/{route_card_id}/operation/{operation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_route_operation(
    route_card_id: int,
    operation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Engineering", "Admin")),
):
    operation = db.scalar(
        select(RouteOperation).where(
            RouteOperation.id == operation_id,
            RouteOperation.route_card_id == route_card_id,
            RouteOperation.is_deleted.is_(False),
        )
    )
    if not operation:
        raise HTTPException(status_code=404, detail="RouteOperation not found")

    route_card = db.scalar(select(RouteCard).where(RouteCard.id == route_card_id))
    if not route_card:
        raise HTTPException(status_code=404, detail="RouteCard not found")
    if route_card.status != RouteCardStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Released RouteCard cannot be edited")

    operation.is_deleted = True
    operation.updated_by = current_user.id
    db.add(operation)
    db.commit()

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROUTE_OPERATION_DELETED",
        table_name="route_operations",
        record_id=operation.id,
    )

    return None
