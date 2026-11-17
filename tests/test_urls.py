import pytest
from httpx import AsyncClient
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import User
from app.services.urls import normalize_url
from tests.test_auth import register

ALICE = "alice@example.com"
BOB = "bob@example.com"


async def auth_headers(client: AsyncClient, email: str = ALICE) -> dict[str, str]:
    user_id = await register(client, email)
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def create_url(
    client: AsyncClient, headers: dict[str, str], url: str = "https://example.com"
) -> int:
    response = await client.post("/urls", json={"url": url}, headers=headers)
    assert response.status_code == 201
    url_id: int = response.json()["id"]
    return url_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Example.COM/", "https://example.com"),
        ("https://example.com:443/status/", "https://example.com/status"),
        ("https://example.com/?q=1", "https://example.com?q=1"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(HttpUrl(raw)) == expected


async def test_create_url_applies_defaults_and_normalizes(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    response = await client.post(
        "/urls", json={"url": "HTTPS://Example.COM/status/"}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://example.com/status"
    assert body["interval_minutes"] == 5
    assert body["is_active"] is True
    assert body["name"] is None


async def test_create_url_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/urls", json={"url": "https://example.com"})

    assert response.status_code == 401


async def test_create_duplicate_url_after_normalization_returns_409(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    await create_url(client, headers, "https://example.com/")

    response = await client.post("/urls", json={"url": "https://EXAMPLE.com"}, headers=headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "URL already monitored", "code": "URL_ALREADY_EXISTS"}


async def test_same_url_for_two_users_is_allowed(client: AsyncClient) -> None:
    await create_url(client, await auth_headers(client, ALICE))
    await create_url(client, await auth_headers(client, BOB))


async def test_create_url_over_limit_returns_409(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_urls_per_user", 1)
    headers = await auth_headers(client)
    await create_url(client, headers, "https://a.example.com")

    response = await client.post("/urls", json={"url": "https://b.example.com"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "URL_LIMIT_REACHED"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://LOCALHOST.:8000/admin",
        "http://api.localhost",
        "http://127.0.0.1",
        "http://2130706433",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0",
        "http://[::1]",
        "http://[::ffff:127.0.0.1]",
        "ftp://example.com",
        "file:///etc/passwd",
    ],
)
async def test_create_forbidden_url_returns_422(client: AsyncClient, url: str) -> None:
    headers = await auth_headers(client)

    response = await client.post("/urls", json={"url": url}, headers=headers)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("interval", [0, 1441])
async def test_create_url_with_invalid_interval_returns_422(
    client: AsyncClient, interval: int
) -> None:
    headers = await auth_headers(client)

    response = await client.post(
        "/urls",
        json={"url": "https://example.com", "interval_minutes": interval},
        headers=headers,
    )

    assert response.status_code == 422


async def test_list_urls_is_scoped_and_paginated(client: AsyncClient) -> None:
    alice = await auth_headers(client, ALICE)
    ids = [await create_url(client, alice, f"https://{n}.example.com") for n in ("a", "b", "c")]
    await create_url(client, await auth_headers(client, BOB), "https://bob.example.com")

    all_urls = await client.get("/urls", headers=alice)
    page = await client.get("/urls", params={"limit": 2, "offset": 1}, headers=alice)

    assert [url["id"] for url in all_urls.json()] == ids
    assert [url["id"] for url in page.json()] == ids[1:]


async def test_list_urls_limit_above_100_returns_422(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    response = await client.get("/urls", params={"limit": 101}, headers=headers)

    assert response.status_code == 422


async def test_get_own_url(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    url_id = await create_url(client, headers)

    response = await client.get(f"/urls/{url_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["url"] == "https://example.com"


async def test_get_unknown_url_returns_404(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    response = await client.get("/urls/999999", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "URL not found", "code": "URL_NOT_FOUND"}


@pytest.mark.parametrize(
    ("method", "body"),
    [("GET", None), ("PATCH", {"name": "hijacked"}), ("DELETE", None)],
)
async def test_access_to_another_users_url_returns_404(
    client: AsyncClient, method: str, body: dict[str, str] | None
) -> None:
    alice = await auth_headers(client, ALICE)
    url_id = await create_url(client, alice)
    bob = await auth_headers(client, BOB)

    response = await client.request(method, f"/urls/{url_id}", json=body, headers=bob)

    assert response.status_code == 404
    assert response.json()["code"] == "URL_NOT_FOUND"
    untouched = await client.get(f"/urls/{url_id}", headers=alice)
    assert untouched.json()["name"] is None


async def test_patch_url_updates_only_given_fields(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    url_id = await create_url(client, headers)
    created = (await client.get(f"/urls/{url_id}", headers=headers)).json()

    response = await client.patch(
        f"/urls/{url_id}",
        json={"url": "https://Example.org/health/", "is_active": False},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "https://example.org/health"
    assert body["is_active"] is False
    assert body["interval_minutes"] == created["interval_minutes"]
    assert body["updated_at"] >= created["updated_at"]


@pytest.mark.parametrize("field", ["url", "interval_minutes", "is_active"])
async def test_patch_url_with_null_required_field_returns_422(
    client: AsyncClient, field: str
) -> None:
    headers = await auth_headers(client)
    url_id = await create_url(client, headers)

    response = await client.patch(f"/urls/{url_id}", json={field: None}, headers=headers)

    assert response.status_code == 422


async def test_patch_url_to_forbidden_host_returns_422(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    url_id = await create_url(client, headers)

    response = await client.patch(
        f"/urls/{url_id}", json={"url": "http://127.0.0.1"}, headers=headers
    )

    assert response.status_code == 422


async def test_patch_url_to_existing_url_returns_409(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    await create_url(client, headers, "https://a.example.com")
    url_id = await create_url(client, headers, "https://b.example.com")

    response = await client.patch(
        f"/urls/{url_id}", json={"url": "https://a.example.com/"}, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "URL_ALREADY_EXISTS"


async def test_delete_url_returns_204(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    url_id = await create_url(client, headers)

    response = await client.delete(f"/urls/{url_id}", headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(f"/urls/{url_id}", headers=headers)).status_code == 404


async def test_valid_token_of_deleted_user_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await register(client)
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    user = await db_session.get(User, user_id)
    await db_session.delete(user)
    await db_session.commit()

    response = await client.get("/urls", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"
