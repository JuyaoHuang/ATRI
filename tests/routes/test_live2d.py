"""Tests for Phase 8 Live2D management routes."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.app import create_app
from src.storage.live2d_storage import Live2DStorage
from src.utils.config_loader import load_config


def _build_live2d_archive(*, include_preview: bool = True) -> bytes:
    buffer = io.BytesIO()
    model_settings = {
        "Version": 3,
        "FileReferences": {
            "Moc": "runtime.moc3",
            "Textures": ["textures/texture_00.png"],
            "Expressions": [
                {"Name": "happy", "File": "expressions/happy.exp3.json"},
                {"Name": "sad", "File": "expressions/sad.exp3.json"},
            ],
        },
    }

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "hiyori/runtime.model3.json", json.dumps(model_settings, ensure_ascii=False)
        )
        archive.writestr("hiyori/runtime.moc3", b"mock-moc3")
        archive.writestr("hiyori/textures/texture_00.png", b"mock-png")
        archive.writestr("hiyori/expressions/happy.exp3.json", "{}")
        archive.writestr("hiyori/expressions/sad.exp3.json", "{}")
        if include_preview:
            archive.writestr("hiyori/preview.png", b"mock-preview")

    return buffer.getvalue()


@pytest_asyncio.fixture
async def client_and_storage(tmp_path: Path):
    """Create test client with isolated Live2D storage."""

    config = load_config("config.yaml")
    app = create_app(config)
    storage = Live2DStorage(models_dir=tmp_path / "models", seed_default=False)
    app.state.live2d_storage = storage

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, storage


@pytest.mark.asyncio
async def test_upload_live2d_archive_extracts_model_and_metadata(client_and_storage):
    client, storage = client_and_storage

    response = await client.post(
        "/api/live2d/models",
        files={"model": ("hiyori.zip", _build_live2d_archive(), "application/zip")},
        data={"name": "Hiyori"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Hiyori"
    assert data["model_path"].endswith(".model3.json")
    assert data["model_url"].startswith("http://test/api/assets/live2d/")
    assert data["thumbnail_url"] is not None
    assert data["expressions"] == ["happy", "sad"]
    assert data["is_default"] is True
    assert storage.get_model(data["id"]).name == "Hiyori"


@pytest.mark.asyncio
async def test_list_live2d_models_returns_saved_records(client_and_storage):
    client, _storage = client_and_storage

    await client.post(
        "/api/live2d/models",
        files={"model": ("first.zip", _build_live2d_archive(), "application/zip")},
        data={"name": "First Model"},
    )
    await client.post(
        "/api/live2d/models",
        files={
            "model": ("second.zip", _build_live2d_archive(include_preview=False), "application/zip")
        },
        data={"name": "Second Model"},
    )

    response = await client.get("/api/live2d/models")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["is_default"] is True
    assert {item["name"] for item in data} == {"First Model", "Second Model"}


@pytest.mark.asyncio
async def test_get_live2d_expressions_returns_expression_names(client_and_storage):
    client, _storage = client_and_storage

    create_response = await client.post(
        "/api/live2d/models",
        files={"model": ("hiyori.zip", _build_live2d_archive(), "application/zip")},
    )
    model_id = create_response.json()["id"]

    response = await client.get(f"/api/live2d/models/{model_id}/expressions")
    assert response.status_code == 200
    assert response.json() == {"model_id": model_id, "expressions": ["happy", "sad"]}


@pytest.mark.asyncio
async def test_delete_live2d_model_removes_directory(client_and_storage):
    client, storage = client_and_storage

    create_response = await client.post(
        "/api/live2d/models",
        files={"model": ("hiyori.zip", _build_live2d_archive(), "application/zip")},
    )
    model_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/live2d/models/{model_id}")
    assert delete_response.status_code == 204
    assert not (storage.models_dir / model_id).exists()

    get_response = await client.get(f"/api/live2d/models/{model_id}/expressions")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_upload_live2d_rejects_invalid_archive(client_and_storage):
    client, _storage = client_and_storage

    response = await client.post(
        "/api/live2d/models",
        files={"model": ("broken.zip", b"not-a-zip", "application/zip")},
    )

    assert response.status_code == 400
    assert "valid ZIP archive" in response.json()["detail"]
