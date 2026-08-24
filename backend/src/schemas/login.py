from pydantic import BaseModel, EmailStr

from src.schemas.auth_cookie import CookieSendStatus


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    message: str
    cookie: CookieSendStatus


class LoginError(BaseModel):
    error: str
