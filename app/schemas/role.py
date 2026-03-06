from datetime import datetime
from pydantic import BaseModel


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class RoleOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleModuleAccessUpdate(BaseModel):
    modules: list[str]


class RoleModuleAccessOut(BaseModel):
    role_id: int
    role_name: str
    modules: list[str]
