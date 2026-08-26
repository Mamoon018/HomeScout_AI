from fastapi import APIRouter, Depends

from src.app.api.dependencies.auth import get_authenticated_user
from src.schemas.authenticated_user import AuthenticatedUser
from src.schemas.welcome import WelcomeResponse
from src.services.welcome.message import get_welcome_message

router = APIRouter(dependencies=[Depends(get_authenticated_user)])


@router.get("/api/user_welcome")
def user_welcome(
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> WelcomeResponse:
    return WelcomeResponse(
        message=get_welcome_message(user_id=user.user_id, user_name=user.user_name)
    )
