from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.rbac import normalize_module_key
from app.db.session import SessionLocal
from app.models.user import User
from app.models.role import Role, RoleModuleAccess


bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    if credentials is None or not credentials.credentials:
        raise credentials_exc

    token = credentials.credentials

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exc
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise credentials_exc

    user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not user or not user.is_active or user.is_locked:
        raise credentials_exc

    role = db.scalar(select(Role).where(Role.id == user.role_id))
    if not role or not role.is_active:
        raise credentials_exc
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None or not credentials.credentials:
        return None

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exc
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise credentials_exc

    user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not user or not user.is_active or user.is_locked:
        raise credentials_exc

    role = db.scalar(select(Role).where(Role.id == user.role_id))
    if not role or not role.is_active:
        raise credentials_exc
    return user


def require_roles(*allowed_roles: str, module: str | None = None):
    inferred_module = module
    if inferred_module is None:
        non_admin_roles = [role_name for role_name in allowed_roles if role_name != "Admin"]
        if non_admin_roles:
            inferred_module = normalize_module_key(non_admin_roles[0])

    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        role = db.scalar(select(Role).where(Role.id == current_user.role_id))
        if not role or not role.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        if role.name == "Admin":
            return current_user

        role_allowed_by_name = role.name in allowed_roles
        module_permissions = {
            access.module_key
            for access in db.scalars(select(RoleModuleAccess).where(RoleModuleAccess.role_id == role.id)).all()
        }

        if module_permissions:
            module_key = normalize_module_key(inferred_module) if inferred_module else None
            if module_key and module_key in module_permissions:
                return current_user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role.name}' does not have module access",
            )

        if not role_allowed_by_name:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return checker

# ...existing code...
# ...existing code...


def get_current_active_user(current_user=Depends(get_current_user)):
    if not current_user.is_active or current_user.is_locked or current_user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive or locked user",
        )
    return current_user
# ...existing code...

# ...existing code...
def get_current_active_admin(
    current_user=Depends(get_current_active_user),
    db=Depends(get_db),
):
    role = db.scalar(select(Role).where(Role.id == current_user.role_id))
    if not role or role.name != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
# ...existing code...
