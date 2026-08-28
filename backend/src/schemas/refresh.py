from pydantic import BaseModel


class RefreshResponse(BaseModel):
    message: str
