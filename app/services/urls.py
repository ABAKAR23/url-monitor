from collections.abc import Sequence
from urllib.parse import urlsplit, urlunsplit

from pydantic import HttpUrl
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import MonitoredUrl, User
from app.schemas.monitored_url import UrlCreate, UrlUpdate


def normalize_url(url: HttpUrl) -> str:
    """HttpUrl met déjà scheme et host en minuscules ; on retire le slash final
    pour que `https://a.com` et `https://a.com/` tombent sur la même contrainte unique."""
    parts = urlsplit(str(url))
    return urlunsplit(parts._replace(path=parts.path.rstrip("/")))


async def _commit_or_conflict(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(409, "URL_ALREADY_EXISTS", "URL already monitored") from None


async def list_urls(
    session: AsyncSession, user: User, limit: int, offset: int
) -> Sequence[MonitoredUrl]:
    result = await session.scalars(
        select(MonitoredUrl)
        .where(MonitoredUrl.user_id == user.id)
        .order_by(MonitoredUrl.id)
        .limit(limit)
        .offset(offset)
    )
    return result.all()


async def get_url(session: AsyncSession, user: User, url_id: int) -> MonitoredUrl:
    monitored_url = await session.scalar(
        select(MonitoredUrl).where(MonitoredUrl.id == url_id, MonitoredUrl.user_id == user.id)
    )
    if monitored_url is None:
        raise AppError(404, "URL_NOT_FOUND", "URL not found")
    return monitored_url


async def create_url(session: AsyncSession, user: User, data: UrlCreate) -> MonitoredUrl:
    count_result = await session.execute(
        select(func.count()).select_from(MonitoredUrl).where(MonitoredUrl.user_id == user.id)
    )
    max_urls = get_settings().max_urls_per_user
    if count_result.scalar_one() >= max_urls:
        raise AppError(409, "URL_LIMIT_REACHED", f"Limit of {max_urls} URLs reached")

    monitored_url = MonitoredUrl(
        user_id=user.id,
        url=normalize_url(data.url),
        name=data.name,
        interval_minutes=data.interval_minutes,
    )
    session.add(monitored_url)
    await _commit_or_conflict(session)
    return monitored_url


async def update_url(
    session: AsyncSession, user: User, url_id: int, data: UrlUpdate
) -> MonitoredUrl:
    monitored_url = await get_url(session, user, url_id)
    changes = data.model_dump(exclude_unset=True)
    if data.url is not None:
        changes["url"] = normalize_url(data.url)
    for field, value in changes.items():
        setattr(monitored_url, field, value)
    await _commit_or_conflict(session)
    # updated_at est calculé par la base : on le recharge explicitement (pas de lazy load en async).
    await session.refresh(monitored_url)
    return monitored_url


async def delete_url(session: AsyncSession, user: User, url_id: int) -> None:
    monitored_url = await get_url(session, user, url_id)
    await session.delete(monitored_url)
    await session.commit()
