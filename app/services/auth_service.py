from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.security import verify_password, get_password_hash
from app.models.user import User
from app.models.role import Role
from app.models.audit_log import AuditLog
from app.core.config import settings

MAX_FAILED_ATTEMPTS = 5
DEFAULT_ROLES = ["Admin", "Sales", "Purchase", "Quality", "Production", "Maintenance", "Dispatch", "Auditor"]


def add_audit_log(
    db: Session,
    user_id: int | None,
    action: str,
    table_name: str | None = None,
    record_id: int | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        user_id=user_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(log)
    db.commit()


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username, User.is_deleted.is_(False)))
    if not user:
        return None
    if not user.is_active or user.is_locked:
        return None
    if user.auth_provider == "google":
        return None

    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
            user.is_locked = True
        db.add(user)
        db.commit()
        add_audit_log(
            db=db,
            user_id=user.id,
            action="LOGIN_FAILED",
            table_name="users",
            record_id=user.id,
            new_value={"failed_attempts": user.failed_attempts, "is_locked": user.is_locked},
        )
        return None

    user.failed_attempts = 0
    db.add(user)
    db.commit()
    add_audit_log(db=db, user_id=user.id, action="LOGIN_SUCCESS", table_name="users", record_id=user.id)
    return user


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    role_id: int,
    created_by: int | None = None,
    auth_provider: str = "local",
) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=get_password_hash(password),
        role_id=role_id,
        auth_provider=auth_provider,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    add_audit_log(
        db=db,
        user_id=created_by,
        action="USER_CREATED",
        table_name="users",
        record_id=user.id,
        new_value={"username": user.username, "email": user.email, "role_id": user.role_id},
    )
    return user


def bootstrap_roles_and_admin(db: Session) -> None:
    existing_roles = {r.name for r in db.scalars(select(Role)).all()}
    for role_name in DEFAULT_ROLES:
        if role_name not in existing_roles:
            db.add(Role(name=role_name))
    db.commit()

    admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
    admin_user = db.scalar(select(User).where(User.username == settings.ADMIN_BOOTSTRAP_USERNAME))
    if not admin_user and admin_role:
        db.add(
            User(
                username=settings.ADMIN_BOOTSTRAP_USERNAME,
                email=settings.ADMIN_BOOTSTRAP_EMAIL,
                password_hash=get_password_hash(settings.ADMIN_BOOTSTRAP_PASSWORD),
                role_id=admin_role.id,
                auth_provider="both",
                is_active=True,
                is_locked=False,
                failed_attempts=0,
                is_deleted=False,
            )
        )
        db.commit()