"""Tests for generation-keyed visual capture coordination."""

from __future__ import annotations

import asyncio

import pytest

from src.vision import InputImage, VisionCaptureCoordinator


def _image() -> InputImage:
    return InputImage(
        source="screen",
        media_type="image/jpeg",
        encoding="base64",
        data="opaque",
    )


@pytest.mark.asyncio
async def test_register_then_resolve_returns_generation_image() -> None:
    coordinator = VisionCaptureCoordinator()
    future = coordinator.register("gen-a")

    assert coordinator.pending_generation_ids == ("gen-a",)
    assert coordinator.resolve("gen-a", _image()) is True
    assert await future == _image()
    assert coordinator.pending_count == 0


@pytest.mark.asyncio
async def test_wait_returns_none_for_unavailable_capture() -> None:
    coordinator = VisionCaptureCoordinator()
    future = coordinator.register("gen-a")
    waiter = asyncio.create_task(coordinator.wait("gen-a", future, timeout_ms=100))

    assert coordinator.resolve("gen-a", None) is True
    assert await waiter is None
    assert coordinator.pending_count == 0


@pytest.mark.asyncio
async def test_duplicate_registration_does_not_replace_pending_future() -> None:
    coordinator = VisionCaptureCoordinator()
    original = coordinator.register("gen-a")

    with pytest.raises(ValueError, match="already pending"):
        coordinator.register("gen-a")

    assert coordinator.pending_count == 1
    assert coordinator.resolve("gen-a", None) is True
    assert await original is None


@pytest.mark.asyncio
async def test_timeout_cancels_and_removes_pending_future() -> None:
    coordinator = VisionCaptureCoordinator()
    future = coordinator.register("gen-a")

    assert await coordinator.wait("gen-a", future, timeout_ms=1) is None
    assert future.cancelled() is True
    assert coordinator.pending_count == 0
    assert coordinator.resolve("gen-a", _image()) is False


@pytest.mark.asyncio
async def test_task_cancellation_cleans_pending_future() -> None:
    coordinator = VisionCaptureCoordinator()
    future = coordinator.register("gen-a")
    waiter = asyncio.create_task(coordinator.wait("gen-a", future, timeout_ms=1000))
    await asyncio.sleep(0)

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert future.cancelled() is True
    assert coordinator.pending_count == 0


@pytest.mark.asyncio
async def test_cancel_all_is_connection_scoped_and_stale_results_are_ignored() -> None:
    coordinator = VisionCaptureCoordinator()
    first = coordinator.register("gen-a")
    second = coordinator.register("gen-b")

    assert coordinator.cancel_all() == 2
    assert first.cancelled() is True
    assert second.cancelled() is True
    assert coordinator.pending_count == 0
    assert coordinator.resolve("gen-a", _image()) is False
    assert coordinator.resolve("unknown", None) is False


@pytest.mark.asyncio
async def test_wait_requires_registered_generation() -> None:
    coordinator = VisionCaptureCoordinator()
    unrelated = asyncio.get_running_loop().create_future()

    with pytest.raises(KeyError, match="No pending capture"):
        await coordinator.wait("missing", unrelated, timeout_ms=100)

    unrelated.cancel()
