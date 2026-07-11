"""Generation-keyed coordination for browser screen capture results.

按 generation 协调浏览器屏幕截图结果。
"""

from __future__ import annotations

import asyncio

from .models import InputImage


class VisionCaptureCoordinator:
    """Own pending capture futures for one WebSocket connection.

    The coordinator is intentionally event-loop local. It does not assemble
    chat turns, persist attachments, or invoke the LLM.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[InputImage | None]] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def pending_generation_ids(self) -> tuple[str, ...]:
        return tuple(self._pending)

    def register(self, generation_id: str) -> asyncio.Future[InputImage | None]:
        """Register a pending result before its capture request is sent."""

        if not isinstance(generation_id, str) or not generation_id:
            raise ValueError("generation_id must be a non-empty string")

        existing = self._pending.get(generation_id)
        if existing is not None and not existing.done():
            raise ValueError(f"Capture already pending for generation {generation_id!r}")
        if existing is not None:
            self._pending.pop(generation_id, None)

        future = asyncio.get_running_loop().create_future()
        self._pending[generation_id] = future
        return future

    def resolve(self, generation_id: str, image: InputImage | None) -> bool:
        """Resolve a known pending generation; ignore unknown or late results."""

        future = self._pending.pop(generation_id, None)
        if future is None or future.done():
            return False
        future.set_result(image)
        return True

    def cancel(self, generation_id: str) -> bool:
        """Cancel and remove one pending generation."""

        future = self._pending.pop(generation_id, None)
        if future is None or future.done():
            return False
        future.cancel()
        return True

    def cancel_all(self) -> int:
        """Cancel all pending captures during disconnect or connection cleanup."""

        generation_ids = tuple(self._pending)
        cancelled = 0
        for generation_id in generation_ids:
            cancelled += int(self.cancel(generation_id))
        return cancelled

    async def wait(
        self,
        generation_id: str,
        future: asyncio.Future[InputImage | None],
        *,
        timeout_ms: int,
    ) -> InputImage | None:
        """Await the Future returned by ``register`` with bounded cleanup."""

        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise ValueError("timeout_ms must be a positive integer")

        current = self._pending.get(generation_id)
        if current is None and not future.done():
            raise KeyError(f"No pending capture for generation {generation_id!r}")
        if current is not None and current is not future:
            raise ValueError(f"Future does not belong to generation {generation_id!r}")

        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout_ms / 1000)
        except TimeoutError:
            self.cancel(generation_id)
            return None
        except asyncio.CancelledError:
            self.cancel(generation_id)
            raise
        finally:
            if self._pending.get(generation_id) is future and future.done():
                self._pending.pop(generation_id, None)
