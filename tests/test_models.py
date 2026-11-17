from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MonitoredUrl, User


async def create_user(session: AsyncSession, email: str = "alice@example.com") -> User:
    user = User(email=email, hashed_password="hash")
    session.add(user)
    await session.flush()
    return user


async def test_user_gets_utc_created_at(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    await db_session.refresh(user)

    assert user.created_at.utcoffset() == timedelta(0)


async def test_uppercase_email_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        await create_user(db_session, email="Alice@Example.com")


async def test_duplicate_url_for_same_user_rejected(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    db_session.add(MonitoredUrl(user_id=user.id, url="https://example.com", interval_minutes=5))
    await db_session.flush()

    db_session.add(MonitoredUrl(user_id=user.id, url="https://example.com", interval_minutes=5))
    with pytest.raises(IntegrityError, match="uq_monitored_urls_user_id_url"):
        await db_session.flush()


async def test_deleting_user_cascades_to_urls(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    db_session.add(MonitoredUrl(user_id=user.id, url="https://example.com", interval_minutes=5))
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()

    count = await db_session.scalar(select(func.count()).select_from(MonitoredUrl))
    assert count == 0
