from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.monitored_url import UrlCreate, UrlOut, UrlUpdate
from app.services import urls as url_service

router = APIRouter(prefix="/urls", tags=["urls"])


@router.get("", response_model=list[UrlOut])
async def list_urls(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UrlOut]:
    urls = await url_service.list_urls(session, user, limit, offset)
    return [UrlOut.model_validate(url) for url in urls]


@router.post("", response_model=UrlOut, status_code=status.HTTP_201_CREATED)
async def create_url(data: UrlCreate, user: CurrentUser, session: SessionDep) -> UrlOut:
    url = await url_service.create_url(session, user, data)
    return UrlOut.model_validate(url)


@router.get("/{url_id}", response_model=UrlOut)
async def get_url(url_id: int, user: CurrentUser, session: SessionDep) -> UrlOut:
    url = await url_service.get_url(session, user, url_id)
    return UrlOut.model_validate(url)


@router.patch("/{url_id}", response_model=UrlOut)
async def update_url(
    url_id: int, data: UrlUpdate, user: CurrentUser, session: SessionDep
) -> UrlOut:
    url = await url_service.update_url(session, user, url_id, data)
    return UrlOut.model_validate(url)


@router.delete("/{url_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_url(url_id: int, user: CurrentUser, session: SessionDep) -> None:
    await url_service.delete_url(session, user, url_id)
