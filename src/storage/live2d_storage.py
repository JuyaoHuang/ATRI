"""Read-only Live2D model catalog backed by administrator-managed folders.

基于管理员维护目录的只读 Live2D 模型目录。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote

from loguru import logger

_ATRI_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LIVE2D_ROOT_DIR = _ATRI_ROOT / "data" / "live2d"
_DEFAULT_LIVE2D_MODELS_DIR = _DEFAULT_LIVE2D_ROOT_DIR / "models"
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_OPTIONAL_FILE_REFERENCE_KEYS = ("Physics", "Pose", "DisplayInfo", "UserData")


class Live2DStorageError(Exception):
    """Base exception for Live2D catalog operations.

    Live2D 模型目录操作的基异常。
    """


class Live2DModelNotFoundError(Live2DStorageError):
    """Raised when a requested model is missing or invalid.

    请求的模型缺失或无效时抛出。
    """


class Live2DModelValidationError(Live2DStorageError):
    """Raised when an installed model cannot be loaded safely.

    已安装模型无法安全加载时抛出。
    """


class _OptionalReferenceMissing(Live2DModelValidationError):
    """Internal signal for a missing non-essential model resource."""


@dataclass(frozen=True)
class Live2DModelRecord:
    """Live2D model metadata derived from one direct child directory.

    从一个直接子目录动态派生的 Live2D 模型元数据。
    """

    id: str
    name: str
    model_path: str
    thumbnail_path: str | None
    expressions: list[str]
    is_default: bool


def get_default_live2d_root_dir() -> Path:
    """Return the default Live2D root directory.

    返回默认的 Live2D 根目录。
    """

    return _DEFAULT_LIVE2D_ROOT_DIR


def get_default_live2d_models_dir() -> Path:
    """Return the default Live2D models directory served as static assets.

    返回默认的 Live2D 模型目录（用作静态资源）。
    """

    return _DEFAULT_LIVE2D_MODELS_DIR


def _is_settings_path(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name.endswith(".model3.json") or name.endswith(".model.json")
    ) and name != "items_pinned_to_model.json"


def _relative_sort_key(path: Path, root: Path) -> tuple[int, int, str, str]:
    relative_path = path.relative_to(root).as_posix()
    return (
        len(PurePosixPath(relative_path).parts),
        len(relative_path),
        relative_path.casefold(),
        relative_path,
    )


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


class Live2DStorage:
    """Discover and validate administrator-installed Live2D model folders.

    发现并校验由管理员安装的 Live2D 模型目录。
    """

    def __init__(
        self,
        models_dir: Path | None = None,
        *,
        default_model_id: str | None = None,
    ) -> None:
        """Initialize a read-only catalog rooted at ``models_dir``.

        使用 ``models_dir`` 初始化只读模型目录。
        """

        self.models_dir = models_dir or get_default_live2d_models_dir()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.default_model_id = (
            default_model_id.strip()
            if isinstance(default_model_id, str) and default_model_id.strip()
            else None
        )

    async def list_models(self) -> list[Live2DModelRecord]:
        """Rescan and return all currently valid Live2D models.

        重新扫描并返回当前所有有效的 Live2D 模型。
        """

        return await asyncio.to_thread(self._list_models)

    async def get_model(self, model_id: str) -> Live2DModelRecord:
        """Rescan and return one valid Live2D model.

        重新扫描并返回一个有效的 Live2D 模型。
        """

        return await asyncio.to_thread(self._get_model, model_id)

    async def list_expressions(self, model_id: str) -> list[str]:
        """Return expression names dynamically derived from one model.

        返回从指定模型动态派生的表情名称。
        """

        return (await self.get_model(model_id)).expressions

    def build_asset_url(self, relative_path: str, base_url: str) -> str:
        """Build an absolute asset URL for an installed Live2D file.

        为已安装的 Live2D 文件构建绝对资源 URL。
        """

        clean_base = base_url.rstrip("/")
        return f"{clean_base}/api/assets/live2d/{quote(relative_path, safe='/')}"

    def _list_models(self) -> list[Live2DModelRecord]:
        records: list[Live2DModelRecord] = []
        root = self.models_dir.resolve()

        try:
            children = sorted(
                self.models_dir.iterdir(),
                key=lambda path: (path.name.casefold(), path.name),
            )
        except OSError as error:
            raise Live2DStorageError(
                f"Unable to scan Live2D models directory '{self.models_dir}': {error}"
            ) from error

        for model_dir in children:
            try:
                if model_dir.is_symlink():
                    raise Live2DModelValidationError(
                        "symbolic-link model directories are not allowed"
                    )
                if not model_dir.is_dir():
                    continue
                if model_dir.resolve().parent != root:
                    raise Live2DModelValidationError(
                        "resolved model directory is not a direct child of the models root"
                    )
                records.append(self._scan_model(model_dir))
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "Skipping invalid Live2D model directory | directory={} | reason={}",
                    model_dir,
                    str(error) or repr(error),
                )

        if self.default_model_id and not any(
            record.id == self.default_model_id for record in records
        ):
            logger.warning(
                "Configured default Live2D model is unavailable | directory={} | reason={}",
                self.models_dir / self.default_model_id,
                "configured directory is missing or invalid",
            )

        return sorted(
            records,
            key=lambda record: (
                not record.is_default,
                record.name.casefold(),
                record.name,
                record.id,
            ),
        )

    def _get_model(self, model_id: str) -> Live2DModelRecord:
        model_dir = self._model_dir(model_id)
        try:
            return self._scan_model(model_dir)
        except Live2DModelValidationError as error:
            logger.warning(
                "Requested Live2D model is invalid | directory={} | reason={}",
                model_dir,
                str(error),
            )
            raise Live2DModelNotFoundError(f"Live2D model '{model_id}' is unavailable") from error
        except (OSError, json.JSONDecodeError) as error:
            logger.warning(
                "Requested Live2D model could not be scanned | directory={} | reason={}",
                model_dir,
                str(error),
            )
            raise Live2DModelNotFoundError(f"Live2D model '{model_id}' is unavailable") from error

    def _scan_model(self, model_dir: Path) -> Live2DModelRecord:
        settings_candidates = self._find_settings_candidates(model_dir)
        if not settings_candidates:
            raise Live2DModelValidationError(
                "no .model3.json or .model.json settings file was found"
            )

        settings_file = settings_candidates[0]
        if len(settings_candidates) > 1:
            logger.warning(
                "Multiple Live2D settings files found; using deterministic first candidate "
                "| directory={} | selected={} | count={}",
                model_dir,
                settings_file.relative_to(model_dir).as_posix(),
                len(settings_candidates),
            )

        data = self._read_settings(settings_file)
        file_references = data.get("FileReferences", {})
        if file_references is None:
            file_references = {}
        if not isinstance(file_references, dict):
            raise Live2DModelValidationError("FileReferences must be a JSON object")

        moc_reference = file_references.get("Moc") or data.get("model")
        self._resolve_reference(
            model_dir,
            settings_file.parent,
            moc_reference,
            label="FileReferences.Moc",
            required=True,
        )

        texture_references = file_references.get("Textures")
        if texture_references is None:
            texture_references = data.get("textures")
        if not isinstance(texture_references, list) or not texture_references:
            raise Live2DModelValidationError(
                "FileReferences.Textures must contain at least one texture path"
            )
        for index, texture_reference in enumerate(texture_references):
            self._resolve_reference(
                model_dir,
                settings_file.parent,
                texture_reference,
                label=f"FileReferences.Textures[{index}]",
                required=True,
            )

        expressions = self._parse_expressions(
            data,
            file_references,
            model_dir,
            settings_file.parent,
        )
        self._validate_optional_references(
            data,
            file_references,
            model_dir,
            settings_file.parent,
        )

        model_path = settings_file.relative_to(model_dir).as_posix()
        thumbnail_path = self._find_preview_path(model_dir)
        return Live2DModelRecord(
            id=model_dir.name,
            name=model_dir.name,
            model_path=model_path,
            thumbnail_path=thumbnail_path,
            expressions=expressions,
            is_default=model_dir.name == self.default_model_id,
        )

    def _find_settings_candidates(self, model_dir: Path) -> list[Path]:
        root = model_dir.resolve()
        candidates: list[Path] = []
        for path in model_dir.rglob("*"):
            try:
                if path.is_symlink() or not path.is_file() or not _is_settings_path(path):
                    continue
                path.resolve().relative_to(root)
            except (OSError, ValueError):
                continue
            candidates.append(path)
        return sorted(candidates, key=lambda path: _relative_sort_key(path, model_dir))

    def _read_settings(self, settings_file: Path) -> dict[str, Any]:
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise Live2DModelValidationError(
                f"settings file '{settings_file.name}' is not valid UTF-8 JSON: {error}"
            ) from error
        if not isinstance(data, dict):
            raise Live2DModelValidationError("model settings JSON must be an object")
        return data

    def _parse_expressions(
        self,
        data: dict[str, Any],
        file_references: dict[str, Any],
        model_dir: Path,
        settings_dir: Path,
    ) -> list[str]:
        expressions = file_references.get("Expressions")
        if expressions is None:
            expressions = data.get("expressions", [])
        if not isinstance(expressions, list):
            logger.warning(
                "Ignoring invalid Live2D expression list | directory={} | reason={}",
                model_dir,
                "Expressions is not an array",
            )
            return []

        names: list[str] = []
        for index, item in enumerate(expressions):
            if not isinstance(item, dict):
                logger.warning(
                    "Ignoring invalid Live2D expression entry | directory={} | reason={}",
                    model_dir,
                    f"Expressions[{index}] is not an object",
                )
                continue

            name = item.get("Name") or item.get("name")
            file_reference = item.get("File") or item.get("file")
            if not isinstance(name, str) or not name.strip():
                logger.warning(
                    "Ignoring unnamed Live2D expression | directory={} | reason={}",
                    model_dir,
                    f"Expressions[{index}] has no name",
                )
                continue

            try:
                self._resolve_reference(
                    model_dir,
                    settings_dir,
                    file_reference,
                    label=f"Expressions[{index}].File",
                    required=False,
                )
            except _OptionalReferenceMissing as error:
                logger.warning(
                    "Ignoring unavailable Live2D expression | directory={} | reason={}",
                    model_dir,
                    str(error),
                )
                continue
            names.append(name.strip())

        return sorted(set(names), key=lambda name: (name.casefold(), name))

    def _validate_optional_references(
        self,
        data: dict[str, Any],
        file_references: dict[str, Any],
        model_dir: Path,
        settings_dir: Path,
    ) -> None:
        for key in _OPTIONAL_FILE_REFERENCE_KEYS:
            value = file_references.get(key)
            if value is None:
                value = data.get(key.casefold())
            if value is None:
                continue
            self._warn_if_optional_reference_missing(
                model_dir,
                settings_dir,
                value,
                label=f"FileReferences.{key}",
            )

        motions = file_references.get("Motions")
        if motions is None:
            motions = data.get("motions")
        if motions is None:
            return
        if not isinstance(motions, dict):
            logger.warning(
                "Ignoring invalid Live2D motions map | directory={} | reason={}",
                model_dir,
                "Motions is not an object",
            )
            return

        for group, entries in motions.items():
            if not isinstance(entries, list):
                logger.warning(
                    "Ignoring invalid Live2D motion group | directory={} | reason={}",
                    model_dir,
                    f"Motions.{group} is not an array",
                )
                continue
            for index, item in enumerate(entries):
                value = item.get("File") or item.get("file") if isinstance(item, dict) else item
                self._warn_if_optional_reference_missing(
                    model_dir,
                    settings_dir,
                    value,
                    label=f"Motions.{group}[{index}].File",
                )

    def _warn_if_optional_reference_missing(
        self,
        model_dir: Path,
        settings_dir: Path,
        value: Any,
        *,
        label: str,
    ) -> None:
        try:
            self._resolve_reference(
                model_dir,
                settings_dir,
                value,
                label=label,
                required=False,
            )
        except _OptionalReferenceMissing as error:
            logger.warning(
                "Optional Live2D resource is unavailable | directory={} | reason={}",
                model_dir,
                str(error),
            )

    def _resolve_reference(
        self,
        model_dir: Path,
        settings_dir: Path,
        raw_reference: Any,
        *,
        label: str,
        required: bool,
    ) -> Path:
        if not isinstance(raw_reference, str) or not raw_reference.strip():
            error_message = f"{label} must be a non-empty relative path"
            if required:
                raise Live2DModelValidationError(error_message)
            raise _OptionalReferenceMissing(error_message)

        reference = raw_reference.strip()
        normalized = reference.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(reference)
        if (
            _has_control_characters(reference)
            or posix_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or ".." in posix_path.parts
        ):
            raise Live2DModelValidationError(f"{label} contains an unsafe path: {raw_reference!r}")

        parts = tuple(part for part in posix_path.parts if part not in {"", "."})
        if not parts:
            error_message = f"{label} must reference a file"
            if required:
                raise Live2DModelValidationError(error_message)
            raise _OptionalReferenceMissing(error_message)

        model_root = model_dir.resolve()
        target = settings_dir.joinpath(*parts)
        resolved_target = target.resolve(strict=False)
        try:
            resolved_target.relative_to(model_root)
        except ValueError as error:
            raise Live2DModelValidationError(
                f"{label} resolves outside the model directory: {raw_reference!r}"
            ) from error

        if not resolved_target.is_file():
            error_message = f"{label} file does not exist: {raw_reference!r}"
            if required:
                raise Live2DModelValidationError(error_message)
            raise _OptionalReferenceMissing(error_message)
        return resolved_target

    def _find_preview_path(self, model_dir: Path) -> str | None:
        root = model_dir.resolve()
        image_candidates: list[Path] = []
        for path in model_dir.rglob("*"):
            try:
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path.suffix.casefold() not in _IMAGE_SUFFIXES
                ):
                    continue
                path.resolve().relative_to(root)
            except (OSError, ValueError):
                continue
            image_candidates.append(path)

        ordered = sorted(
            image_candidates,
            key=lambda path: _relative_sort_key(path, model_dir),
        )
        preview_candidates = [path for path in ordered if path.name.casefold() == "preview.png"]
        selected = (preview_candidates or ordered)[0] if ordered else None
        return selected.relative_to(model_dir).as_posix() if selected else None

    def _model_dir(self, model_id: str) -> Path:
        self._validate_model_id(model_id)
        model_dir = self.models_dir / model_id
        try:
            if model_dir.is_symlink() or not model_dir.is_dir():
                raise Live2DModelNotFoundError(f"Live2D model '{model_id}' not found")
            if model_dir.resolve().parent != self.models_dir.resolve():
                raise Live2DModelNotFoundError(f"Live2D model '{model_id}' not found")
        except OSError as error:
            raise Live2DModelNotFoundError(f"Live2D model '{model_id}' not found") from error
        return model_dir

    @staticmethod
    def _validate_model_id(model_id: str) -> None:
        if (
            not isinstance(model_id, str)
            or not model_id
            or model_id in {".", ".."}
            or "/" in model_id
            or "\\" in model_id
            or _has_control_characters(model_id)
        ):
            raise Live2DModelNotFoundError("Invalid Live2D model id")

        posix_path = PurePosixPath(model_id)
        windows_path = PureWindowsPath(model_id)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or len(posix_path.parts) != 1
        ):
            raise Live2DModelNotFoundError("Invalid Live2D model id")


__all__ = [
    "Live2DModelNotFoundError",
    "Live2DModelRecord",
    "Live2DModelValidationError",
    "Live2DStorage",
    "Live2DStorageError",
    "get_default_live2d_models_dir",
    "get_default_live2d_root_dir",
]
