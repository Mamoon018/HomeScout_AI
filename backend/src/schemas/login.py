from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_token: str


class LoginResponse(BaseModel):
    message: str
    user_id: str
    user_name: str | None = None


class LoginError(BaseModel):
    error: str
