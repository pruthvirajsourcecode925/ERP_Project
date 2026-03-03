from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_active_admin, get_optional_current_user
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.auth_service import create_user as create_user_service, add_audit_log

router = APIRouter()

@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    existing_email = db.query(User).filter(User.email == user.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    existing_username = db.query(User).filter(User.username == user.username).first()
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already registered")

    role_id = user.role_id
    requested_role_name = user.role
    if user.role:
        role = db.scalar(select(Role).where(Role.name == user.role))
        if not role:
            raise HTTPException(status_code=400, detail=f"Role '{user.role}' not found")
        role_id = role.id

    if role_id is None:
        raise HTTPException(status_code=400, detail="Either role or role_id is required")

    role_exists = db.scalar(select(Role).where(Role.id == role_id))
    if not role_exists:
        raise HTTPException(status_code=400, detail=f"Role id '{role_id}' not found")

    target_role_name = requested_role_name or role_exists.name
    if target_role_name == "Admin":
        if not current_user:
            raise HTTPException(status_code=403, detail="Admin access required to create an admin user")

        current_user_role = db.scalar(select(Role).where(Role.id == current_user.role_id))
        if not current_user_role or current_user_role.name != "Admin":
            raise HTTPException(status_code=403, detail="Admin access required to create an admin user")

    new_user = create_user_service(
        db=db,
        username=user.username,
        email=user.email,
        password=user.password,
        role_id=role_id,
        created_by=current_user.id if current_user else None,
        auth_provider=user.auth_provider,
    )
    return new_user

@router.get("/{user_id}", response_model=UserResponse)
def read_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"] != db_user.email:
        email_exists = db.query(User).filter(User.email == update_data["email"], User.id != user_id).first()
        if email_exists:
            raise HTTPException(status_code=400, detail="Email already registered")

    if "username" in update_data and update_data["username"] != db_user.username:
        username_exists = db.query(User).filter(User.username == update_data["username"], User.id != user_id).first()
        if username_exists:
            raise HTTPException(status_code=400, detail="Username already registered")

    if "role_id" in update_data and update_data["role_id"] is not None:
        role_exists = db.scalar(select(Role).where(Role.id == update_data["role_id"]))
        if not role_exists:
            raise HTTPException(status_code=400, detail=f"Role id '{update_data['role_id']}' not found")

    if "password" in update_data and update_data["password"]:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
    else:
        update_data.pop("password", None)

    for key, value in update_data.items():
        setattr(db_user, key, value)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/", response_model=list[UserResponse])
def list_users(
    username: str | None = None,
    role: str | None = None,
    is_locked: bool | None = None,
    auth_provider: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """List non-deleted users with optional filters. Admin only."""
    stmt = select(User).where(User.is_deleted.is_(False))

    if username:
        stmt = stmt.where(User.username.ilike(f"%{username}%"))

    if role:
        role_obj = db.scalar(select(Role).where(Role.name == role))
        if not role_obj:
            return []
        stmt = stmt.where(User.role_id == role_obj.id)

    if is_locked is not None:
        stmt = stmt.where(User.is_locked == is_locked)

    if auth_provider:
        if auth_provider not in {"local", "google", "both"}:
            raise HTTPException(status_code=400, detail="Invalid auth_provider. Use one of: local, google, both")
        stmt = stmt.where(User.auth_provider == auth_provider)

    users = db.scalars(stmt.order_by(User.id.desc()).offset(skip).limit(limit)).all()
    return users


@router.post("/{user_id}/unlock", response_model=UserResponse)
def unlock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    db_user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.is_locked = False
    db_user.failed_attempts = 0
    db_user.updated_by = current_user.id
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_UNLOCKED",
        table_name="users",
        record_id=db_user.id,
        new_value={"is_locked": False, "failed_attempts": 0},
    )
    return db_user


@router.post("/{user_id}/disable", response_model=UserResponse)
def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    db_user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")

    db_user.is_active = False
    db_user.updated_by = current_user.id
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_DISABLED",
        table_name="users",
        record_id=db_user.id,
        new_value={"is_active": False},
    )
    return db_user


@router.post("/{user_id}/enable", response_model=UserResponse)
def enable_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    db_user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.is_active = True
    db_user.updated_by = current_user.id
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_ENABLED",
        table_name="users",
        record_id=db_user.id,
        new_value={"is_active": True},
    )
    return db_user


@router.post("/{user_id}/soft-delete", response_model=UserResponse)
def soft_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    db_user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot soft-delete yourself")

    db_user.is_deleted = True
    db_user.is_active = False
    db_user.updated_by = current_user.id
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_SOFT_DELETED",
        table_name="users",
        record_id=db_user.id,
        old_value={"username": db_user.username, "email": db_user.email},
        new_value={"is_deleted": True, "is_active": False},
    )
    return db_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Hard-delete a user (permanently remove from database). Admin only."""
    db_user = db.scalar(select(User).where(User.id == user_id))
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    # Remove FK references before hard delete
    db.execute(
        update(User)
        .where(User.created_by == db_user.id)
        .values(created_by=None)
    )
    db.execute(
        update(User)
        .where(User.updated_by == db_user.id)
        .values(updated_by=None)
    )
    db.execute(
        update(AuditLog)
        .where(AuditLog.user_id == db_user.id)
        .values(user_id=None)
    )

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_HARD_DELETED",
        table_name="users",
        record_id=db_user.id,
        old_value={"username": db_user.username, "email": db_user.email},
    )

    db.delete(db_user)
    db.commit()
    return None
    return None