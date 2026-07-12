"""Tests for the read-only Live2D model catalog routes."""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from loguru import logger

from src.app import create_app
from src.storage import live2d_storage as live2d_storage_module
from src.storage.live2d_storage import Live2DModelNotFoundError, Live2DStorage
from src.utils.config_loader import load_config


def _write_live2d_model(
    models_dir: Path,
    model_id: str,
    *,
    settings_path: str = "runtime/model.model3.json",
    moc_reference: str = "model.moc3",
    texture_references: list[str] | None = None,
    expressions: list[dict[str, str]] | None = None,
    include_moc: bool = True,
    include_textures: bool = True,
    include_preview: bool = True,
) -> Path:
    """Create a small metadata-free Live2D directory for route tests."""

    model_dir = models_dir / model_id
    settings_file = model_dir.joinpath(*settings_path.split("/"))
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    texture_references = texture_references or ["textures/texture_00.png"]
    expressions = expressions or [
        {"Name": "happy", "File": "expressions/happy.exp3.json"},
        {"Name": "sad", "File": "expressions/sad.exp3.json"},
    ]
    settings = {
        "Version": 3,
        "FileReferences": {
            "Moc": moc_reference,
            "Textures": texture_references,
            "Expressions": expressions,
        },
    }
    settings_file.write_text(json.dumps(settings), encoding="utf-8")

    if include_moc:
        moc_file = settings_file.parent.joinpath(*moc_reference.replace("\\", "/").split("/"))
        moc_file.parent.mkdir(parents=True, exist_ok=True)
        moc_file.write_bytes(b"mock-moc3")

    if include_textures:
        for texture_reference in texture_references:
            texture_file = settings_file.parent.joinpath(
                *texture_reference.replace("\\", "/").split("/")
            )
            texture_file.parent.mkdir(parents=True, exist_ok=True)
            texture_file.write_bytes(b"mock-texture")

    for expression in expressions:
        expression_reference = expression.get("File") or expression.get("file")
        if not expression_reference:
            continue
        expression_file = settings_file.parent.joinpath(
            *expression_reference.replace("\\", "/").split("/")
        )
        expression_file.parent.mkdir(parents=True, exist_ok=True)
        expression_file.write_text("{}", encoding="utf-8")

    if include_preview:
        (model_dir / "preview.png").write_bytes(b"mock-preview")
    return model_dir


@pytest_asyncio.fixture
async def client_and_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, Live2DStorage, Path]]:
    """Create an app whose API and static mount share an isolated model root."""

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(
        live2d_storage_module,
        "_DEFAULT_LIVE2D_MODELS_DIR",
        models_dir,
    )

    config = load_config("config.yaml")
    app = create_app(config)
    storage = Live2DStorage(models_dir=models_dir)
    app.state.live2d_storage = storage

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, storage, models_dir


@pytest.mark.asyncio
async def test_list_discovers_metadata_free_direct_model_directory(client_and_storage):
    client, _storage, models_dir = client_and_storage
    _write_live2d_model(models_dir, "mao_pro")

    response = await client.get("/api/live2d/models")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "mao_pro",
            "name": "mao_pro",
            "model_path": "runtime/model.model3.json",
            "model_url": "http://test/api/assets/live2d/mao_pro/runtime/model.model3.json",
            "thumbnail_url": "http://test/api/assets/live2d/mao_pro/preview.png",
            "expressions": ["happy", "sad"],
            "is_default": False,
        }
    ]
    assert not (models_dir / "mao_pro" / "metadata.json").exists()

    settings_response = await client.get(response.json()[0]["model_url"])
    assert settings_response.status_code == 200
    assert settings_response.json()["FileReferences"]["Moc"] == "model.moc3"


@pytest.mark.asyncio
async def test_catalog_rescans_after_admin_adds_and_removes_directory(client_and_storage):
    client, _storage, models_dir = client_and_storage

    assert (await client.get("/api/live2d/models")).json() == []

    _write_live2d_model(models_dir, "late_model")
    added = await client.get("/api/live2d/models")
    assert [model["id"] for model in added.json()] == ["late_model"]

    shutil.rmtree(models_dir / "late_model")
    assert (await client.get("/api/live2d/models")).json() == []


@pytest.mark.asyncio
async def test_invalid_directory_is_warned_and_does_not_hide_valid_models(client_and_storage):
    client, _storage, models_dir = client_and_storage
    _write_live2d_model(models_dir, "valid_model")
    (models_dir / "copy_in_progress").mkdir()

    warnings: list[str] = []
    sink_id = logger.add(warnings.append, level="WARNING", format="{message}")
    try:
        response = await client.get("/api/live2d/models")
    finally:
        logger.remove(sink_id)

    assert response.status_code == 200
    assert [model["id"] for model in response.json()] == ["valid_model"]
    assert any("copy_in_progress" in warning for warning in warnings)
    assert any("no .model3.json" in warning for warning in warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_resource", ["moc", "texture"])
async def test_missing_required_resource_skips_model(client_and_storage, missing_resource: str):
    client, _storage, models_dir = client_and_storage
    _write_live2d_model(
        models_dir,
        "incomplete_model",
        include_moc=missing_resource != "moc",
        include_textures=missing_resource != "texture",
    )

    response = await client.get("/api/live2d/models")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_reference_traversal_skips_model_even_when_target_exists(client_and_storage):
    client, _storage, models_dir = client_and_storage
    outside_moc = models_dir / "outside.moc3"
    outside_moc.write_bytes(b"outside")
    _write_live2d_model(
        models_dir,
        "unsafe_model",
        moc_reference="../../outside.moc3",
        include_moc=False,
    )

    response = await client.get("/api/live2d/models")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_multiple_settings_files_use_deterministic_candidate(client_and_storage):
    client, _storage, models_dir = client_and_storage
    model_dir = _write_live2d_model(
        models_dir,
        "multi_settings",
        settings_path="nested/long_name.model3.json",
    )
    root_settings = model_dir / "root.model3.json"
    root_settings.write_text(
        json.dumps(
            {
                "FileReferences": {
                    "Moc": "root.moc3",
                    "Textures": ["root.png"],
                }
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "root.moc3").write_bytes(b"moc")
    (model_dir / "root.png").write_bytes(b"texture")

    response = await client.get("/api/live2d/models")

    assert response.status_code == 200
    assert response.json()[0]["model_path"] == "root.model3.json"


@pytest.mark.asyncio
async def test_configured_default_is_marked_without_forcing_first_item(client_and_storage):
    client, storage, models_dir = client_and_storage
    _write_live2d_model(models_dir, "alpha")
    _write_live2d_model(models_dir, "preferred")
    storage.default_model_id = "preferred"

    response = await client.get("/api/live2d/models")

    assert response.status_code == 200
    defaults = [model["id"] for model in response.json() if model["is_default"]]
    assert defaults == ["preferred"]


@pytest.mark.asyncio
async def test_missing_configured_default_does_not_promote_first_model(client_and_storage):
    client, storage, models_dir = client_and_storage
    _write_live2d_model(models_dir, "only_model")
    storage.default_model_id = "missing_model"

    warnings: list[str] = []
    sink_id = logger.add(warnings.append, level="WARNING", format="{message}")
    try:
        response = await client.get("/api/live2d/models")
    finally:
        logger.remove(sink_id)

    assert response.status_code == 200
    assert response.json()[0]["is_default"] is False
    assert any("missing_model" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_expression_route_rescans_model_settings(client_and_storage):
    client, _storage, models_dir = client_and_storage
    model_dir = _write_live2d_model(models_dir, "expressive")

    response = await client.get("/api/live2d/models/expressive/expressions")
    assert response.status_code == 200
    assert response.json() == {
        "model_id": "expressive",
        "expressions": ["happy", "sad"],
    }

    settings_file = model_dir / "runtime" / "model.model3.json"
    settings: dict[str, Any] = json.loads(settings_file.read_text(encoding="utf-8"))
    settings["FileReferences"]["Expressions"] = [
        {"Name": "surprised", "File": "expressions/surprised.exp3.json"}
    ]
    settings_file.write_text(json.dumps(settings), encoding="utf-8")
    expression_file = model_dir / "runtime" / "expressions" / "surprised.exp3.json"
    expression_file.write_text("{}", encoding="utf-8")

    rescanned = await client.get("/api/live2d/models/expressive/expressions")
    assert rescanned.json()["expressions"] == ["surprised"]


@pytest.mark.asyncio
async def test_missing_optional_expression_is_omitted_without_invalidating_model(
    client_and_storage,
):
    client, _storage, models_dir = client_and_storage
    _write_live2d_model(
        models_dir,
        "optional_expression",
        expressions=[
            {"Name": "missing", "File": "expressions/missing.exp3.json"},
        ],
    )
    (models_dir / "optional_expression" / "runtime" / "expressions" / "missing.exp3.json").unlink()

    response = await client.get("/api/live2d/models")

    assert response.status_code == 200
    assert response.json()[0]["expressions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_id",
    ["", ".", "..", "../model", "model/child", "model\\child", "C:model", "C:\\model", "bad\x00id"],
)
async def test_model_lookup_rejects_unsafe_ids(tmp_path: Path, model_id: str):
    storage = Live2DStorage(models_dir=tmp_path / "models")

    with pytest.raises(Live2DModelNotFoundError):
        await storage.get_model(model_id)


@pytest.mark.asyncio
async def test_symlink_model_directory_is_skipped(tmp_path: Path):
    models_dir = tmp_path / "models"
    real_model = _write_live2d_model(models_dir, "real_model")
    link_model = models_dir / "linked_model"
    try:
        link_model.symlink_to(real_model, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")

    records = await Live2DStorage(models_dir=models_dir).list_models()

    assert [record.id for record in records] == ["real_model"]


@pytest.mark.asyncio
async def test_mutation_routes_are_absent_and_leave_model_files_unchanged(client_and_storage):
    client, _storage, models_dir = client_and_storage
    model_dir = _write_live2d_model(models_dir, "read_only")
    before = {
        path.relative_to(model_dir).as_posix(): path.read_bytes()
        for path in model_dir.rglob("*")
        if path.is_file()
    }

    responses = [
        await client.post(
            "/api/live2d/models",
            files={"model": ("model.zip", b"not-used", "application/zip")},
        ),
        await client.put("/api/live2d/models/read_only", json={"name": "renamed"}),
        await client.delete("/api/live2d/models/read_only"),
    ]

    assert all(response.status_code in {404, 405} for response in responses)
    after = {
        path.relative_to(model_dir).as_posix(): path.read_bytes()
        for path in model_dir.rglob("*")
        if path.is_file()
    }
    assert after == before

    openapi = (await client.get("/openapi.json")).json()
    assert set(openapi["paths"]["/api/live2d/models"]) == {"get"}
    assert set(openapi["paths"]["/api/live2d/models/{model_id}/expressions"]) == {"get"}


@pytest.mark.asyncio
async def test_repository_hiyori_model_uses_flat_metadata_free_layout():
    config = load_config("config.yaml")
    storage = Live2DStorage(
        default_model_id=config["live2d"]["default_model"],
    )

    record = await storage.get_model("hiyori_free_zh")

    assert record.id == "hiyori_free_zh"
    assert record.name == "hiyori_free_zh"
    assert record.model_path == "runtime/hiyori_free_t08.model3.json"
    assert record.is_default is True
    assert not (storage.models_dir / "hiyori_free_zh" / "metadata.json").exists()
