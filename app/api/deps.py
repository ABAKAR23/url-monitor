from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.models import User

# auto_error=False : l'absence de token passe par AppError pour garder le format d'erreur uniforme.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> User:
    if token is None:
        raise AppError(401, "NOT_AUTHENTICATED", "Not authenticated")
    user_id = decode_access_token(token)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise AppError(401, "INVALID_TOKEN", "Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
