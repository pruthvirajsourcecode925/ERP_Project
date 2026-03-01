from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_db
from app.models.role import Role
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut
from app.services.auth_service import add_audit_log

router = APIRouter(tags=["Roles"])


@router.get("/", response_model=list[RoleOut])
def list_roles(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_admin),
):
    """List all roles. Admin only."""
    roles = db.scalars(select(Role).offset(skip).limit(limit)).all()
    return roles


@router.get("/{role_id}", response_model=RoleOut)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_admin),
):
    """Get a single role by ID. Admin only."""
    role = db.scalar(select(Role).where(Role.id == role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.post("/", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    role_in: RoleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_admin),
):
    """Create a new role. Admin only."""
    existing = db.scalar(select(Role).where(Role.name == role_in.name))
    if existing:
        raise HTTPException(status_code=400, detail="Role name already exists")

    role = Role(
        name=role_in.name,
        description=role_in.description,
        is_active=role_in.is_active,
    )
    db.add(role)
    db.commit()
    db.refresh(role)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROLE_CREATED",
        table_name="roles",
        record_id=role.id,
        new_value={"name": role.name, "description": role.description},
    )
    return role


@router.put("/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int,
    role_in: RoleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_admin),
):
    """Update a role. Admin only."""
    role = db.scalar(select(Role).where(Role.id == role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    old_values = {"name": role.name, "description": role.description, "is_active": role.is_active}

    update_data = role_in.model_dump(exclude_unset=True)

    # Check for name conflict if changing name
    if "name" in update_data and update_data["name"] != role.name:
        conflict = db.scalar(select(Role).where(Role.name == update_data["name"]))
        if conflict:
            raise HTTPException(status_code=400, detail="Role name already exists")

    for key, value in update_data.items():
        setattr(role, key, value)

    db.commit()
    db.refresh(role)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROLE_UPDATED",
        table_name="roles",
        record_id=role.id,
        old_value=old_values,
        new_value=update_data,
    )
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_admin),
):
    """Deactivate a role (set is_active=False). Admin only."""
    role = db.scalar(select(Role).where(Role.id == role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Prevent deactivating Admin role
    if role.name == "Admin":
        raise HTTPException(status_code=400, detail="Cannot deactivate Admin role")

    role.is_active = False
    db.commit()

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="ROLE_DEACTIVATED",
        table_name="roles",
        record_id=role.id,
        new_value={"is_active": False},
    )
    return None
