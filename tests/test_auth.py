from datetime import timedelta

import jwt
from httpx import AsyncClient

from app.core.security import JWT_ALGORITHM, create_access_token

EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery"


async def register(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD) -> int:
    response = await client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    user_id: int = response.json()["id"]
    return user_id


async def login(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD) -> str:
    response = await client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200
    token: str = response.json()["access_token"]
    return token


async def test_register_returns_user_with_normalized_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "Alice@Example.com", "password": PASSWORD}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert set(body) == {"id", "email", "created_at"}


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await register(client)

    response = await client.post(
        "/auth/register", json={"email": "ALICE@example.com", "password": PASSWORD}
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Email already registered",
        "code": "EMAIL_ALREADY_EXISTS",
    }


async def test_register_invalid_payload_returns_uniform_422(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={"email": "nope", "password": "short"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "email" in body["detail"]
    assert "password" in body["detail"]
    assert "short" not in body["detail"]


async def test_login_returns_bearer_token(client: AsyncClient) -> None:
    await register(client)

    response = await client.post(
        "/auth/login", data={"username": "Alice@Example.COM", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await register(client)

    response = await client.post(
        "/auth/login", data={"username": EMAIL, "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Incorrect email or password",
        "code": "INVALID_CREDENTIALS",
    }


async def test_login_unknown_email_returns_same_401(client: AsyncClient) -> None:
    await register(client)
    wrong_password = await client.post(
        "/auth/login", data={"username": EMAIL, "password": "wrong-password"}
    )

    unknown_email = await client.post(
        "/auth/login", data={"username": "bob@example.com", "password": PASSWORD}
    )

    assert unknown_email.status_code == 401
    assert unknown_email.json() == wrong_password.json()


async def test_me_with_token_returns_current_user(client: AsyncClient) -> None:
    user_id = await register(client)
    token = await login(client)

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["id"] == user_id
    assert response.json()["email"] == EMAIL


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated", "code": "NOT_AUTHENTICATED"}


async def test_me_with_expired_token_returns_401(client: AsyncClient) -> None:
    user_id = await register(client)
    token = create_access_token(user_id, expires_delta=timedelta(minutes=-1))

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


async def test_me_with_token_signed_by_another_secret_returns_401(client: AsyncClient) -> None:
    user_id = await register(client)
    forged = jwt.encode({"sub": str(user_id), "exp": 9999999999}, "x" * 32, JWT_ALGORITHM)

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


async def test_unknown_route_uses_uniform_error_format(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "NOT_FOUND"}
