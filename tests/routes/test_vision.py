"""Tests for visual configuration REST routes."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient

from src.app import create_app
from src.utils.config_loader import load_config
from src.vision import VisionConfigStore, VisionService


@pytest_asyncio.fixture
async def client_and_config_path(tmp_path: Path):
    config = load_config("config.yaml")
    app = create_app(config)
    config_path = tmp_path / "vision_config.yaml"
    app.state.vision_service = VisionService(VisionConfigStore(config["vision"], path=config_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, config_path


@pytest.mark.asyncio
async def test_get_vision_config_returns_complete_safe_config(client_and_config_path) -> None:
    client, _ = client_and_config_path

    response = await client.get("/api/vision/config")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["source"] == "screen"
    assert data["capture"]["media_type"] == "image/jpeg"
    assert data["provider"]["detail"] == "auto"
    assert "media_stream" not in data
    assert "connection_state" not in data


@pytest.mark.asyncio
async def test_put_vision_config_persists_only_enabled(client_and_config_path) -> None:
    client, config_path = client_and_config_path

    response = await client.put("/api/vision/config", json={"enabled": True})

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == {"enabled": True}

    repeated = await client.put("/api/vision/config", json={"enabled": True})
    assert repeated.status_code == 200
    assert repeated.json()["enabled"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"enabled": 1},
        {"enabled": "true"},
        {"source": "screen"},
        {"capture": {}},
        {"provider": {}},
        {"transport": {}},
        {"enabled": True, "source": "screen"},
    ],
)
async def test_put_vision_config_rejects_non_allowlisted_payloads(
    client_and_config_path,
    payload: dict[str, object],
) -> None:
    client, config_path = client_and_config_path

    response = await client.put("/api/vision/config", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Vision config update must contain only a boolean 'enabled' field"
    }
    assert not config_path.exists()
