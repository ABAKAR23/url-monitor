import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_SECRET = "x" * 32
DB_URL = "postgresql+asyncpg://user:pass@localhost:5433/db"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET", "JWT_EXPIRE_MINUTES"):
        monkeypatch.delenv(name, raising=False)


def test_loads_from_env_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("JWT_SECRET", VALID_SECRET)

    settings = Settings(_env_file=None)

    assert settings.database_url == DB_URL
    assert settings.jwt_secret.get_secret_value() == VALID_SECRET
    assert settings.jwt_expire_minutes == 30
    assert settings.max_urls_per_user == 50


def test_secret_is_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("JWT_SECRET", VALID_SECRET)

    assert VALID_SECRET not in repr(Settings(_env_file=None))


def test_missing_jwt_secret_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)

    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None)


def test_short_jwt_secret_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("JWT_SECRET", "too-short")

    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(_env_file=None)


def test_expire_minutes_out_of_range_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("JWT_SECRET", VALID_SECRET)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "0")

    with pytest.raises(ValidationError, match="jwt_expire_minutes"):
        Settings(_env_file=None)
