from src.tts.sentence_divider import SentenceDivider


def test_sentence_divider_emits_complete_chinese_sentence() -> None:
    divider = SentenceDivider(faster_first_response=False)

    assert divider.feed("你好，我正在整理资料") == []
    segments = divider.feed("。下一句还没结束")

    assert [segment.tts_text for segment in segments] == ["你好，我正在整理资料。"]
    assert [segment.sequence for segment in segments] == [0]
    assert divider.buffer == "下一句还没结束"


def test_sentence_divider_faster_first_response_splits_on_short_pause() -> None:
    divider = SentenceDivider(faster_first_response=True)

    segments = divider.feed("你好，我刚才在整理资料。")

    assert [segment.tts_text for segment in segments] == ["你好，", "我刚才在整理资料。"]
    assert [segment.sequence for segment in segments] == [0, 1]
    assert divider.buffer == ""


def test_sentence_divider_can_wait_for_full_sentence_before_first_response() -> None:
    divider = SentenceDivider(faster_first_response=False)

    segments = divider.feed("你好，我刚才在整理资料。")

    assert [segment.tts_text for segment in segments] == ["你好，我刚才在整理资料。"]
    assert [segment.sequence for segment in segments] == [0]


def test_sentence_divider_accepts_english_sentence_boundaries() -> None:
    divider = SentenceDivider(faster_first_response=False)

    segments = divider.feed("Hello world. Next sentence")

    assert [segment.tts_text for segment in segments] == ["Hello world."]
    assert [segment.sequence for segment in segments] == [0]
    assert divider.buffer == "Next sentence"


def test_sentence_divider_accepts_japanese_sentence_boundaries() -> None:
    divider = SentenceDivider(faster_first_response=False)

    segments = divider.feed("こんにちは。次です．まだ途中")

    assert [segment.tts_text for segment in segments] == ["こんにちは。", "次です．"]
    assert [segment.sequence for segment in segments] == [0, 1]
    assert divider.buffer == "まだ途中"


def test_sentence_divider_flush_emits_remaining_buffer() -> None:
    divider = SentenceDivider(faster_first_response=False)
    assert divider.feed("还有半句") == []

    segments = divider.flush()

    assert [segment.tts_text for segment in segments] == ["还有半句"]
    assert [segment.sequence for segment in segments] == [0]
    assert divider.buffer == ""


def test_sentence_divider_ignores_blank_and_punctuation_only_text() -> None:
    divider = SentenceDivider(faster_first_response=True)

    assert divider.feed("   ") == []
    assert divider.feed("！！！．．｡") == []
    assert divider.flush() == []
