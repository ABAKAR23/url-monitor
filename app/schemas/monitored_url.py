from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.core.ssrf import is_forbidden_host

URL_MAX_LENGTH = 2048
DEFAULT_INTERVAL_MINUTES = 5


def _check_public_url(url: HttpUrl) -> HttpUrl:
    if len(str(url)) > URL_MAX_LENGTH:
        raise ValueError(f"must be at most {URL_MAX_LENGTH} characters")
    if url.host is None or is_forbidden_host(url.host):
        raise ValueError("private or local addresses are not allowed")
    return url


PublicHttpUrl = Annotated[HttpUrl, AfterValidator(_check_public_url)]
IntervalMinutes = Annotated[int, Field(ge=1, le=1440)]


class UrlCreate(BaseModel):
    url: PublicHttpUrl
    name: str | None = Field(default=None, max_length=100)
    interval_minutes: IntervalMinutes = DEFAULT_INTERVAL_MINUTES


class UrlUpdate(BaseModel):
    url: PublicHttpUrl | None = None
    name: str | None = Field(default=None, max_length=100)
    interval_minutes: IntervalMinutes | None = None
    is_active: bool | None = None

    @field_validator("url", "interval_minutes", "is_active")
    @classmethod
    def not_null(cls, value: object) -> object:
        """`None` signifie "champ absent" ; un `null` explicite viderait une colonne NOT NULL."""
        if value is None:
            raise ValueError("must not be null")
        return value


class UrlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    name: str | None
    interval_minutes: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
