from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class GoogleCallbackRequest(BaseModel):
    code: str


class GoogleLoginResponse(BaseModel):
    authorization_url: str
    state: str


class MessageResponse(BaseModel):
    message: str


class BootstrapAdminRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
