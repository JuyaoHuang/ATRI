"""Visual configuration application service.

视觉配置应用服务。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .config import VisionConfigStore
from .exceptions import VisionConfigError

VISION_CONFIG_WRITE_FIELDS = {"enabled"}


class VisionService:
    """Expose the safe visual configuration boundary used by routes."""

    def __init__(self, config_store: VisionConfigStore) -> None:
        self.config_store = config_store

    def get_config(self) -> dict[str, Any]:
        """Return the complete safe visual configuration."""

        return self.config_store.read()

    def is_enabled(self) -> bool:
        """Return whether the visual module is globally available."""

        return bool(self.config_store.read()["enabled"])

    async def update_config(
        self,
        patch: dict[str, Any],
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Persist the allowlisted visual configuration update."""

        fields = set(patch)
        unsupported = sorted(fields - VISION_CONFIG_WRITE_FIELDS)
        if unsupported:
            raise VisionConfigError(f"Unsupported vision config fields: {', '.join(unsupported)}")
        if fields != VISION_CONFIG_WRITE_FIELDS:
            raise VisionConfigError("Vision config update requires exactly the 'enabled' field")

        enabled = patch["enabled"]
        if type(enabled) is not bool:
            raise VisionConfigError("vision.enabled must be a boolean")

        if not persist:
            return self.config_store.update_enabled(enabled, persist=False)
        return await asyncio.to_thread(self.config_store.update_enabled, enabled, persist=True)
