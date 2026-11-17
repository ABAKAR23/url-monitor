import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.models import User
from app.schemas.user import UserCreate


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def register(session: AsyncSession, data: UserCreate) -> User:
    hashed_password = await asyncio.to_thread(hash_password, data.password)
    user = User(email=normalize_email(data.email), hashed_password=hashed_password)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "Email already registered") from None
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    hashed_password = user.hashed_password if user else DUMMY_PASSWORD_HASH
    is_valid = await asyncio.to_thread(verify_password, password, hashed_password)
    if user is None or not is_valid:
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password")
    return user
