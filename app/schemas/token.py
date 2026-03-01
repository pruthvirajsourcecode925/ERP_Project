from pydantic import BaseModel
from datetime import datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class SessionOut(BaseModel):
    session_id: int
    created_at: datetime
    expires_at: datetime