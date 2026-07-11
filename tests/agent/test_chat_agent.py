"""Tests for src/agent/chat_agent.py -- streaming + collect dual interface.

Covers Phase 4 PRD US-AGT-003 acceptance criteria (success path only; the
error-path tests are added in US-AGT-004).

测试要点（US-AGT-003 成功路径）：
  (a) chat() 按顺序 yield mock 流的每个 chunk
  (b) build_llm_context 被恰好 await 一次，user_input 原样传入、
      system_prompt 等于 persona.system_prompt
  (c) on_round_complete 在流结束后恰好 await 一次，user_msg.content ==
      user_input 原样，ai_msg.content == 所 yield chunks 的拼接、
      ai_msg.name == persona.name
  (d) chat_collect() 返回 ''.join(chunks)，且 on_round_complete 只 await 一次
  (e) 成功路径不调 append_system_note
  (f) persona.system_prompt 为空串也能正常工作（build_llm_context 收到 ''）
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.chat_agent import ChatAgent
from src.agent.persona import Persona
from src.llm.exceptions import (
    LLMAPIError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
)
from src.vision import InputImage, InputInform, InputText

# ---------------------------------------------------------------------------
# Test helpers
# 测试辅助函数
# ---------------------------------------------------------------------------


def _persona(system_prompt: str = "You are Atri.") -> Persona:
    """Build a Persona instance for tests.

    构造测试用 Persona 实例。
    """
    return Persona(
        character_id="atri",
        name="亚托莉",
        avatar=None,
        greeting=None,
        system_prompt=system_prompt,
    )


async def _astream(chunks: list[str]) -> AsyncIterator[str]:
    """Yield given chunks asynchronously to simulate an LLM stream.

    异步产出给定的 chunks 列表，以模拟 LLM 流。
    """
    for c in chunks:
        yield c


def _make_llm(chunks: list[str]) -> MagicMock:
    """Build a MagicMock that returns a fresh async stream per call.

    side_effect creates a new async generator on each call, so tests that
    invoke chat() twice won't share the same exhausted generator.

    构造每次调用都返回新异步流的 MagicMock。

    使用 side_effect 保证每次调用都新建一个异步生成器；若测试多次调用
    chat()，也不会复用已耗尽的生成器。
    """
    llm = MagicMock()
    llm.chat_completion_stream = MagicMock(side_effect=lambda *a, **kw: _astream(chunks))
    return llm


def _make_mgr(
    build_context_return: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a MagicMock MemoryManager with awaitable build_llm_context /
    on_round_complete and a synchronous append_system_note.

    构造 MagicMock MemoryManager：build_llm_context / on_round_complete 为
    可 await 的异步 mock，append_system_note 为同步 mock。
    """
    mgr = MagicMock()
    mgr.build_llm_context = AsyncMock(
        return_value=build_context_return or [{"role": "user", "content": "ctx"}]
    )
    mgr.on_round_complete = AsyncMock()
    mgr.append_system_note = MagicMock()
    return mgr


# ---------------------------------------------------------------------------
# chat() streaming behavior
# chat() 的流式行为
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_yields_chunks_in_order() -> None:
    """chat() yields every chunk from the mocked stream in insertion order.

    chat() 按插入顺序产出 mock 流中的每个 chunk。
    """
    chunks = ["Hello", ", ", "world", "!"]
    agent = ChatAgent(_make_llm(chunks), _make_mgr(), _persona())

    received = [c async for c in agent.chat("hi")]

    assert received == chunks


@pytest.mark.asyncio
async def test_build_llm_context_called_with_raw_user_input() -> None:
    """build_llm_context receives user_input verbatim + system_prompt kwarg.

    build_llm_context 收到原样 user_input 以及 system_prompt 关键字参数。
    """
    agent = ChatAgent(_make_llm(["x"]), _make_mgr(), _persona("SYS"))

    raw = "  原样 USER  input   😊  "  # 带前后空格和 emoji，应全部保留
    [_ async for _ in agent.chat(raw)]

    agent.memory_manager.build_llm_context.assert_awaited_once_with(
        raw,
        system_prompt="SYS",
    )


@pytest.mark.asyncio
async def test_runtime_context_passed_to_builder_but_not_committed() -> None:
    mgr = _make_mgr()
    agent = ChatAgent(_make_llm(["ok"]), mgr, _persona("SYS"))
    runtime_context = {
        "datetime": {
            "iso": "2026-04-25T04:34:00.000Z",
            "local": "2026/4/25 12:34:00",
        }
    }

    [_ async for _ in agent.chat("what time is it?", runtime_context=runtime_context)]

    mgr.build_llm_context.assert_awaited_once_with(
        "what time is it?",
        system_prompt="SYS",
        runtime_context=runtime_context,
    )
    user_msg, _ai_msg = mgr.on_round_complete.await_args.args
    assert user_msg == {"role": "human", "content": "what time is it?"}


@pytest.mark.asyncio
async def test_llm_stream_called_with_build_context_result() -> None:
    """chat_completion_stream is called with the messages list that
    build_llm_context returned.

    chat_completion_stream 收到 build_llm_context 返回的 messages 列表。
    """
    context = [
        {"role": "system", "content": "You are Atri."},
        {"role": "user", "content": "hi"},
    ]
    agent = ChatAgent(_make_llm(["ok"]), _make_mgr(context), _persona())

    [_ async for _ in agent.chat("hi")]

    assert agent.llm.chat_completion_stream.call_count == 1
    call_args = agent.llm.chat_completion_stream.call_args
    # 必须把 build_llm_context 的结果原样转发
    # Must forward build_llm_context's result unchanged.
    assert call_args.args[0] is context


@pytest.mark.asyncio
async def test_multimodal_input_sends_image_only_to_llm_boundary() -> None:
    context = [{"role": "user", "content": "describe the screen"}]
    mgr = _make_mgr(context)
    llm = _make_llm(["ok"])
    agent = ChatAgent(llm, mgr, _persona())
    image = InputImage(
        source="screen",
        media_type="image/jpeg",
        encoding="base64",
        data="opaque-image",
    )
    input_inform = InputInform(
        input_text=InputText("describe the screen"),
        image=image,
    )

    [_ async for _ in agent.chat(input_inform)]

    mgr.build_llm_context.assert_awaited_once_with(
        "describe the screen",
        system_prompt="You are Atri.",
    )
    llm.chat_completion_stream.assert_called_once_with(context, input_image=image)
    user_msg, _ai_msg = mgr.on_round_complete.await_args.args
    assert user_msg == {"role": "human", "content": "describe the screen"}
    assert "opaque-image" not in repr(mgr.build_llm_context.await_args)


# ---------------------------------------------------------------------------
# on_round_complete auto-commit
# 自动提交 on_round_complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_round_complete_awaited_once_after_stream_exhausts() -> None:
    """After stream exhausts, on_round_complete is awaited exactly once.

    The user_msg carries the raw user_input; the ai_msg carries
    ''.join(chunks) as content and persona.name as the name field.

    流结束后 on_round_complete 恰好 await 一次。
    user_msg 承载原样 user_input；ai_msg 的 content == ''.join(chunks)，
    name == persona.name。
    """
    chunks = ["abc", "def", "ghi"]
    persona = _persona()
    agent = ChatAgent(_make_llm(chunks), _make_mgr(), persona)

    [_ async for _ in agent.chat("ping")]

    agent.memory_manager.on_round_complete.assert_awaited_once()
    call = agent.memory_manager.on_round_complete.await_args
    user_msg, ai_msg = call.args
    assert user_msg == {"role": "human", "content": "ping"}
    assert ai_msg == {
        "role": "ai",
        "content": "abcdefghi",
        "name": persona.name,
    }


@pytest.mark.asyncio
async def test_on_round_complete_not_called_before_stream_exhausts() -> None:
    """on_round_complete is NOT awaited during streaming -- only after.

    流式过程中不 await on_round_complete；仅在流结束后 await 一次。
    """
    chunks = ["a", "b", "c"]
    agent = ChatAgent(_make_llm(chunks), _make_mgr(), _persona())

    seen_completes_during_stream: list[int] = []
    async for _ in agent.chat("hi"):
        # 流式过程中不应已被 await
        # Must not have been awaited mid-stream.
        seen_completes_during_stream.append(agent.memory_manager.on_round_complete.await_count)

    assert all(c == 0 for c in seen_completes_during_stream)
    assert agent.memory_manager.on_round_complete.await_count == 1


@pytest.mark.asyncio
async def test_chat_can_skip_automatic_round_commit() -> None:
    """WebSocket VAD paths commit only after generation guards pass."""

    agent = ChatAgent(_make_llm(["safe"]), _make_mgr(), _persona())

    received = [chunk async for chunk in agent.chat("hi", commit_round=False)]

    assert received == ["safe"]
    agent.memory_manager.on_round_complete.assert_not_awaited()


# ---------------------------------------------------------------------------
# chat_collect() non-streaming interface
# chat_collect() 非流式接口
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_collect_returns_joined_reply() -> None:
    """chat_collect() returns ''.join(chunks) from the same mocked stream.

    chat_collect() 返回与 chat() 同一 mock 流的 ''.join(chunks)。
    """
    chunks = ["one ", "two ", "three"]
    agent = ChatAgent(_make_llm(chunks), _make_mgr(), _persona())

    result = await agent.chat_collect("hello")

    assert result == "one two three"


@pytest.mark.asyncio
async def test_chat_collect_commits_round_exactly_once() -> None:
    """chat_collect() reuses chat()'s commit path -- on_round_complete
    fires exactly once (not twice, not zero).

    chat_collect() 复用 chat() 的提交路径——on_round_complete 恰好触发一次
    （不是两次，也不是零次）。
    """
    agent = ChatAgent(_make_llm(["ok"]), _make_mgr(), _persona())

    await agent.chat_collect("hi")

    assert agent.memory_manager.on_round_complete.await_count == 1


@pytest.mark.asyncio
async def test_chat_collect_can_skip_automatic_round_commit() -> None:
    agent = ChatAgent(_make_llm(["ok"]), _make_mgr(), _persona())

    result = await agent.chat_collect("hi", commit_round=False)

    assert result == "ok"
    agent.memory_manager.on_round_complete.assert_not_awaited()


# ---------------------------------------------------------------------------
# Edge cases
# 边界情况
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_path_does_not_call_append_system_note() -> None:
    """Success path never touches the error-note hook.

    成功路径绝不调用错误哨兵钩子。
    """
    agent = ChatAgent(_make_llm(["ok"]), _make_mgr(), _persona())

    [_ async for _ in agent.chat("hi")]

    agent.memory_manager.append_system_note.assert_not_called()


@pytest.mark.asyncio
async def test_empty_system_prompt_still_works() -> None:
    """persona.system_prompt == '' (empty string) propagates to build_llm_context.

    persona.system_prompt 为空串时，build_llm_context 仍收到 ''（而非 None）。
    """
    agent = ChatAgent(_make_llm(["a"]), _make_mgr(), _persona(system_prompt=""))

    received = [c async for c in agent.chat("hi")]

    assert received == ["a"]
    agent.memory_manager.build_llm_context.assert_awaited_once_with(
        "hi",
        system_prompt="",
    )


@pytest.mark.asyncio
async def test_empty_stream_still_commits_round_with_empty_reply() -> None:
    """A zero-chunk stream commits a round whose ai_msg.content is ''.

    零 chunk 流仍会提交一轮，其 ai_msg.content 为 ''。
    """
    agent = ChatAgent(_make_llm([]), _make_mgr(), _persona())

    received = [c async for c in agent.chat("ping")]

    assert received == []
    agent.memory_manager.on_round_complete.assert_awaited_once()
    _user_msg, ai_msg = agent.memory_manager.on_round_complete.await_args.args
    assert ai_msg["content"] == ""


# ---------------------------------------------------------------------------
# Error-path tests -- LLMError remains exception control flow
# 错误路径测试——LLMError 保持异常控制流
# ---------------------------------------------------------------------------


async def _astream_then_raise(chunks_before: list[str], exc: BaseException) -> AsyncIterator[str]:
    """Yield ``chunks_before`` then raise ``exc`` on the next __anext__.

    产出 ``chunks_before``，然后在下一次 __anext__ 时抛出 ``exc``。
    """
    for c in chunks_before:
        yield c
    raise exc


def _make_failing_llm(
    chunks_before: list[str],
    exc: BaseException,
) -> MagicMock:
    """LLM mock whose stream yields ``chunks_before`` then raises ``exc``.

    返回一个 LLM mock：流先产出 ``chunks_before``，再抛出 ``exc``。
    """
    llm = MagicMock()
    llm.chat_completion_stream = MagicMock(
        side_effect=lambda *a, **kw: _astream_then_raise(chunks_before, exc)
    )
    return llm


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_cls",
    [LLMConnectionError, LLMRateLimitError, LLMAPIError],
)
async def test_all_llmerror_subclasses_propagate(exc_cls: type[LLMError]) -> None:
    exc = exc_cls("boom")
    agent = ChatAgent(_make_failing_llm([], exc), _make_mgr(), _persona())

    with pytest.raises(exc_cls) as raised:
        [_ async for _ in agent.chat("hi")]

    assert raised.value is exc
    agent.memory_manager.append_system_note.assert_not_called()
    agent.memory_manager.on_round_complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_immediate_failure_yields_no_error_text() -> None:
    agent = ChatAgent(
        _make_failing_llm([], LLMConnectionError("network down")),
        _make_mgr(),
        _persona(),
    )

    received: list[str] = []
    with pytest.raises(LLMConnectionError, match="network down"):
        async for chunk in agent.chat("hi"):
            received.append(chunk)

    assert received == []
    agent.memory_manager.append_system_note.assert_not_called()
    agent.memory_manager.on_round_complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_stream_preserves_yielded_chunks_before_error() -> None:
    """Partial chunks stay observable, then the original error propagates."""
    agent = ChatAgent(
        _make_failing_llm(["hello ", "world"], LLMAPIError("backend 500")),
        _make_mgr(),
        _persona(),
    )

    received: list[str] = []
    with pytest.raises(LLMAPIError, match="backend 500"):
        async for chunk in agent.chat("hi"):
            received.append(chunk)

    assert received == ["hello ", "world"]
    agent.memory_manager.append_system_note.assert_not_called()
    agent.memory_manager.on_round_complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_original_llm_error_instance_is_not_rewrapped() -> None:
    error = LLMRateLimitError("429 too many")
    agent = ChatAgent(
        _make_failing_llm([], error),
        _make_mgr(),
        _persona(),
    )

    with pytest.raises(LLMRateLimitError) as raised:
        [_ async for _ in agent.chat("hi")]

    assert raised.value is error


@pytest.mark.asyncio
async def test_non_llmerror_exceptions_propagate_not_swallowed() -> None:
    """ValueError from a buggy stream propagates -- chat() does not swallow it.

    从 buggy 流中抛出的 ValueError 会被原样传播，chat() 不吞。
    """
    agent = ChatAgent(
        _make_failing_llm([], ValueError("not an LLMError")),
        _make_mgr(),
        _persona(),
    )

    with pytest.raises(ValueError, match="not an LLMError"):
        [_ async for _ in agent.chat("hi")]

    # 既未尝试写 system note 也未提交本轮
    # Neither system-note write nor round commit attempted.
    agent.memory_manager.append_system_note.assert_not_called()
    agent.memory_manager.on_round_complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_collect_propagates_llm_error() -> None:
    agent = ChatAgent(
        _make_failing_llm(["partial "], LLMAPIError("boom")),
        _make_mgr(),
        _persona(),
    )

    with pytest.raises(LLMAPIError, match="boom"):
        await agent.chat_collect("hi")

    agent.memory_manager.append_system_note.assert_not_called()
    agent.memory_manager.on_round_complete.assert_not_awaited()
