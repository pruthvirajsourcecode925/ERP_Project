from datetime import datetime
from pydantic import BaseModel, EmailStr, model_validator


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str | None = None
    role_id: int | None = None
    auth_provider: str = "local"

    @model_validator(mode="after")
    def validate_role_or_role_id(self):
        if self.role_id is None and not self.role:
            raise ValueError("Either role or role_id is required")
        return self


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    role_id: int | None = None
    is_active: bool | None = None
    is_locked: bool | None = None


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role_id: int
    auth_provider: str
    is_active: bool
    is_locked: bool
    failed_attempts: int
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None
    is_deleted: bool

    model_config = {"from_attributes": True}


# Keep compatibility with users.py imports
class UserResponse(UserOut):
    pass