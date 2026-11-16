from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: SecretStr
    jwt_expire_minutes: int = Field(default=30, ge=1, le=1440)

    max_urls_per_user: int = Field(default=50, ge=1)

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(f"must be at least {JWT_SECRET_MIN_LENGTH} characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
