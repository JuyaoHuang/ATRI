"""Live2D model storage backed by extracted ZIP archives."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from uuid import uuid4

from fastapi import UploadFile
from loguru import logger

DEFAULT_HIYORI_NAME = "Hiyori (Free)"
ALLOWED_ZIP_CONTENT_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LIVE2D_ROOT_DIR = _PROJECT_ROOT / "data" / "live2d"
_DEFAULT_LIVE2D_MODELS_DIR = _DEFAULT_LIVE2D_ROOT_DIR / "models"
_DEFAULT_AIRI_HIYORI_ARCHIVE = (
    _PROJECT_ROOT / "airi" / ".cache" / "live2d" / "models" / "hiyori_free_zh.zip"
)


class Live2DStorageError(Exception):
    """Base exception for Live2D storage operations."""


class Live2DModelNotFoundError(Live2DStorageError):
    """Raised when a model directory or metadata file is missing."""


class Live2DArchiveValidationError(Live2DStorageError):
    """Raised when an uploaded archive is invalid."""


@dataclass(frozen=True)
class Live2DModelRecord:
    """Stored Live2D model metadata."""

    id: str
    name: str
    model_path: str
    thumbnail_path: str | None
    expressions: list[str]
    created_at: str
    is_default: bool


def get_default_live2d_root_dir() -> Path:
    """Return the default Live2D root directory."""

    return _DEFAULT_LIVE2D_ROOT_DIR


def get_default_live2d_models_dir() -> Path:
    """Return the default Live2D models directory served as static assets."""

    return _DEFAULT_LIVE2D_MODELS_DIR


def _now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _is_settings_path(path: str) -> bool:
    return (path.endswith(".model3.json") or path.endswith(".model.json")) and not path.endswith(
        "items_pinned_to_model.json"
    )


def _normalize_archive_path(raw_name: str) -> Path:
    normalized = raw_name.replace("\\", "/").strip("/")
    if not normalized:
        raise Live2DArchiveValidationError("Archive contains an empty file path")
    return Path(*PurePosixPath(normalized).parts)


def _derive_model_name(filename: str) -> str:
    stem = Path(filename).stem.strip()
    if not stem:
        return "Live2D Model"
    return stem.replace("_", " ").replace("-", " ").strip()


class Live2DStorage:
    """Read and write Live2D models from extracted ZIP archives."""

    def __init__(self, models_dir: Path | None = None, *, seed_default: bool | None = None) -> None:
        self.models_dir = models_dir or get_default_live2d_models_dir()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.seed_default = (
            self.models_dir == get_default_live2d_models_dir()
            if seed_default is None
            else seed_default
        )
        self._default_seed_attempted = False

    def list_models(self) -> list[Live2DModelRecord]:
        """List all available Live2D models."""

        self.ensure_default_model()
        records = [
            self.get_model(path.name) for path in sorted(self.models_dir.iterdir()) if path.is_dir()
        ]
        return sorted(
            records, key=lambda record: (not record.is_default, record.name.casefold(), record.id)
        )

    def get_model(self, model_id: str) -> Live2DModelRecord:
        """Load one Live2D model metadata record."""

        model_dir = self._model_dir(model_id)
        metadata_path = model_dir / "metadata.json"
        if not metadata_path.is_file():
            raise Live2DModelNotFoundError(f"Live2D model '{model_id}' not found")

        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return Live2DModelRecord(
            id=data["id"],
            name=data["name"],
            model_path=data["model_path"],
            thumbnail_path=data.get("thumbnail_path"),
            expressions=list(data.get("expressions", [])),
            created_at=data["created_at"],
            is_default=bool(data.get("is_default", False)),
        )

    async def save_model(
        self, archive: UploadFile, *, name: str | None = None
    ) -> Live2DModelRecord:
        """Persist an uploaded Live2D ZIP archive."""

        archive_name = archive.filename or "live2d-model.zip"
        if Path(archive_name).suffix.lower() != ".zip":
            raise Live2DArchiveValidationError("Only ZIP archives are supported for Live2D models")

        if archive.content_type and archive.content_type not in ALLOWED_ZIP_CONTENT_TYPES:
            raise Live2DArchiveValidationError("Unsupported Live2D archive content type")

        payload = await archive.read()
        if not payload:
            raise Live2DArchiveValidationError("Uploaded Live2D archive is empty")

        return self._save_archive_bytes(payload, archive_name, name=name)

    def delete_model(self, model_id: str) -> None:
        """Delete a stored Live2D model."""

        record = self.get_model(model_id)
        model_dir = self._model_dir(record.id)
        shutil.rmtree(model_dir)

        if record.is_default:
            remaining = self.list_models()
            if remaining:
                replacement = remaining[0]
                self._write_metadata(
                    Live2DModelRecord(
                        id=replacement.id,
                        name=replacement.name,
                        model_path=replacement.model_path,
                        thumbnail_path=replacement.thumbnail_path,
                        expressions=replacement.expressions,
                        created_at=replacement.created_at,
                        is_default=True,
                    )
                )

    def list_expressions(self, model_id: str) -> list[str]:
        """Return the model's available expression names."""

        return self.get_model(model_id).expressions

    def build_asset_url(self, relative_path: str, base_url: str) -> str:
        """Build an absolute asset URL for a stored Live2D file."""

        clean_base = base_url.rstrip("/")
        return f"{clean_base}/api/assets/live2d/{quote(relative_path)}"

    def ensure_default_model(self) -> None:
        """Best-effort seed of AIRI's cached Hiyori model for local development."""

        if not self.seed_default or self._default_seed_attempted:
            return
        self._default_seed_attempted = True
        if any(path.is_dir() for path in self.models_dir.iterdir()):
            return
        if not _DEFAULT_AIRI_HIYORI_ARCHIVE.is_file():
            return

        logger.info(
            "Seeding default Live2D model from AIRI cache | archive={}",
            _DEFAULT_AIRI_HIYORI_ARCHIVE,
        )
        try:
            self._save_archive_bytes(
                _DEFAULT_AIRI_HIYORI_ARCHIVE.read_bytes(),
                _DEFAULT_AIRI_HIYORI_ARCHIVE.name,
                name=DEFAULT_HIYORI_NAME,
                force_default=True,
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to seed default Live2D model | error={!r}", error)

    def _save_archive_bytes(
        self,
        payload: bytes,
        archive_name: str,
        *,
        name: str | None = None,
        force_default: bool = False,
    ) -> Live2DModelRecord:
        model_id = f"live2d-{uuid4().hex[:8]}"
        model_dir = self._model_dir(model_id)
        model_dir.mkdir(parents=True, exist_ok=False)

        try:
            settings_path, preview_path, expressions = self._extract_archive(payload, model_dir)
            record = Live2DModelRecord(
                id=model_id,
                name=(name or _derive_model_name(archive_name)).strip() or "Live2D Model",
                model_path=settings_path,
                thumbnail_path=preview_path,
                expressions=expressions,
                created_at=_now_iso_z(),
                is_default=force_default
                or not any(
                    path.is_dir() for path in self.models_dir.iterdir() if path.name != model_id
                ),
            )
            if record.is_default:
                self._clear_default_flags()
            self._write_metadata(record)
            logger.info("Live2D model saved | id={} | name={}", record.id, record.name)
            return record
        except Exception:
            shutil.rmtree(model_dir, ignore_errors=True)
            raise

    def _extract_archive(
        self,
        payload: bytes,
        model_dir: Path,
    ) -> tuple[str, str | None, list[str]]:
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                file_names = [name for name in archive.namelist() if not name.endswith("/")]
                settings_candidates = [name for name in file_names if _is_settings_path(name)]
                if not settings_candidates:
                    raise Live2DArchiveValidationError(
                        "Live2D archive must contain a .model3.json or .model.json file"
                    )

                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    relative_path = _normalize_archive_path(info.filename)
                    target_path = (model_dir / relative_path).resolve()
                    if not str(target_path).startswith(str(model_dir.resolve())):
                        raise Live2DArchiveValidationError("Archive contains an unsafe file path")
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target_path.open("wb") as target:
                        shutil.copyfileobj(source, target)
        except Live2DArchiveValidationError:
            raise
        except zipfile.BadZipFile as error:
            raise Live2DArchiveValidationError(
                "Uploaded file is not a valid ZIP archive"
            ) from error

        settings_candidates.sort(key=lambda item: (item.count("/"), len(item)))
        settings_relative_path = _normalize_archive_path(settings_candidates[0]).as_posix()
        settings_file = model_dir / settings_relative_path
        if not settings_file.is_file():
            raise Live2DArchiveValidationError("Live2D settings file could not be extracted")

        expressions = self._parse_expressions(settings_file)
        preview_relative_path = self._find_preview_path(model_dir)
        return settings_relative_path, preview_relative_path, expressions

    def _parse_expressions(self, settings_file: Path) -> list[str]:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        file_references = data.get("FileReferences", {})
        expressions = file_references.get("Expressions") or data.get("expressions") or []
        names = [
            name
            for item in expressions
            if isinstance(item, dict)
            for name in [item.get("Name")]
            if isinstance(name, str) and name
        ]
        return sorted(dict.fromkeys(names))

    def _find_preview_path(self, model_dir: Path) -> str | None:
        preview_candidates = sorted(model_dir.rglob("preview.png"))
        if preview_candidates:
            return preview_candidates[0].relative_to(model_dir).as_posix()

        image_candidates = sorted(
            path
            for path in model_dir.rglob("*")
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )
        if image_candidates:
            return image_candidates[0].relative_to(model_dir).as_posix()
        return None

    def _clear_default_flags(self) -> None:
        for path in self.models_dir.iterdir():
            metadata_path = path / "metadata.json"
            if not metadata_path.is_file():
                continue
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            if data.get("is_default"):
                data["is_default"] = False
                metadata_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )

    def _write_metadata(self, record: Live2DModelRecord) -> None:
        metadata_path = self._model_dir(record.id) / "metadata.json"
        metadata_path.write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _model_dir(self, model_id: str) -> Path:
        return self.models_dir / model_id


__all__ = [
    "DEFAULT_HIYORI_NAME",
    "Live2DArchiveValidationError",
    "Live2DModelNotFoundError",
    "Live2DModelRecord",
    "Live2DStorage",
    "Live2DStorageError",
    "get_default_live2d_models_dir",
    "get_default_live2d_root_dir",
]
