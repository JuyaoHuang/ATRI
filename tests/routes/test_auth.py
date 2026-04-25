"""Tests for Phase 11 authentication route wiring."""

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from src.app import create_app


def _base_config(auth_config: dict) -> dict:
    return {
        "server": {"cors": {"enabled": False}},
        "auth": auth_config,
        "storage": {"mode": "json", "json": {"base_path": "data/chats"}},
        "llm": {},
        "memory": {},
    }


def _enabled_auth_config() -> dict:
    return {
        "enabled": True,
        "jwt": {"secret_key": "test-secret", "algorithm": "HS256", "expire_days": 7},
        "github": {
            "client_id": "github-client",
            "client_secret": "github-secret",
            "callback_url": "http://localhost:8430/api/auth/callback",
            "scope": "read:user",
        },
        "frontend": {
            "callback_url": "http://localhost:5173/auth/callback",
            "login_url": "http://localhost:5173/login",
        },
        "whitelist": {"users": ["JuyaoHuang"]},
    }


@pytest.mark.asyncio
async def test_auth_status_disabled() -> None:
    app = create_app(_base_config({"enabled": False}))

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


@pytest.mark.asyncio
async def test_auth_me_returns_default_user_when_disabled() -> None:
    app = create_app(_base_config({"enabled": False}))

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "username": "default",
        "avatar_url": None,
        "name": None,
        "auth_enabled": False,
    }


@pytest.mark.asyncio
async def test_auth_login_returns_github_authorization_url_when_enabled() -> None:
    app = create_app(_base_config(_enabled_auth_config()))

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/auth/login?state=nonce")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True

    authorization_url = data["authorization_url"]
    parsed = urlparse(authorization_url)
    params = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "github.com"
    assert parsed.path == "/login/oauth/authorize"
    assert params["client_id"] == ["github-client"]
    assert params["redirect_uri"] == ["http://localhost:8430/api/auth/callback"]
    assert params["scope"] == ["read:user"]
    assert params["state"] == ["nonce"]


@pytest.mark.asyncio
async def test_auth_me_requires_token_when_enabled() -> None:
    app = create_app(_base_config(_enabled_auth_config()))

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


@pytest.mark.asyncio
async def test_auth_me_returns_token_user_when_enabled() -> None:
    app = create_app(_base_config(_enabled_auth_config()))
    token = app.state.auth_service.jwt_manager.create_token(
        "JuyaoHuang",
        avatar_url="https://avatar.example/me.png",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "username": "JuyaoHuang",
        "avatar_url": "https://avatar.example/me.png",
        "name": None,
        "auth_enabled": True,
    }


@pytest.mark.asyncio
async def test_auth_middleware_rejects_protected_routes_without_token() -> None:
    app = create_app(_base_config(_enabled_auth_config()))

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/chats")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


@pytest.mark.asyncio
async def test_protected_chat_routes_use_authenticated_user() -> None:
    app = create_app(_base_config(_enabled_auth_config()))
    app.state.storage = AsyncMock()
    app.state.storage.list_chats.return_value = []
    token = app.state.auth_service.jwt_manager.create_token("JuyaoHuang")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/chats",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == []
    app.state.storage.list_chats.assert_awaited_once_with("JuyaoHuang", None)
