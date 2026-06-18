"""Tests for Phase 9 ASR routes."""

from __future__ import annotations

import asyncio
import io
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient

from src.app import create_app
from src.asr import ASRConfigStore, ASRService
from src.asr.exceptions import ASRTranscriptionError
from src.asr.interface import ASRAudioUploadMetadata, ASRHealth, ASRInterface
from src.asr.providers import faster_whisper as faster_whisper_module
from src.asr.providers import sherpa_onnx_asr as sherpa_onnx_module
from src.utils.config_loader import load_config


def _build_pcm_wav_bytes(
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    num_frames: int = 320,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * num_frames * channels)
    return buffer.getvalue()


class _DummyASR(ASRInterface):
    def transcribe_np(self, audio):  # type: ignore[override]
        return "dummy"


class _CountingASR(ASRInterface):
    # 测试用 provider：记录创建后的调用次数和并发情况，验证常驻缓存行为。
    def __init__(self, text: str = "dummy", *, delay: float = 0.0) -> None:
        super().__init__()
        self.text = text
        self.delay = delay
        self.calls = 0
        self.preload_calls = 0
        self.active_calls = 0
        self.max_active_calls = 0

    def health(self) -> ASRHealth:
        return ASRHealth(True)

    def transcribe_np(self, audio):  # type: ignore[override]
        return self.text

    async def async_transcribe_audio(self, audio: bytes, **kwargs):  # type: ignore[override]
        self.calls += 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return self.text
        finally:
            self.active_calls -= 1

    async def async_preload(self) -> None:
        self.preload_calls += 1


@pytest_asyncio.fixture
async def client_and_config_path(tmp_path: Path):
    """Create test client with isolated ASR config persistence."""

    config = load_config("config.yaml")
    app = create_app(config)
    config_path = tmp_path / "asr_config.yaml"
    app.state.asr_service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "web_speech_api",
                "auto_send": {"enabled": False, "delay_ms": 2000},
            },
            path=config_path,
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, config_path


@pytest.mark.asyncio
async def test_list_asr_providers_returns_registered_statuses(client_and_config_path):
    client, _config_path = client_and_config_path

    response = await client.get("/api/asr/providers")

    assert response.status_code == 200
    providers = response.json()
    names = {provider["name"] for provider in providers}
    assert {
        "web_speech_api",
        "faster_whisper",
        "sherpa_onnx_asr",
        "whisper_cpp",
        "openai_whisper",
    } <= names

    web_speech = next(provider for provider in providers if provider["name"] == "web_speech_api")
    assert web_speech["active"] is True
    assert web_speech["supports_backend_transcription"] is False
    assert web_speech["supports_browser_streaming"] is True


@pytest.mark.asyncio
async def test_update_asr_config_persists_olv_shaped_config(client_and_config_path):
    client, config_path = client_and_config_path

    response = await client.put(
        "/api/asr/config",
        json={
            "asr_model": "web_speech_api",
            "auto_send": {"enabled": True, "delay_ms": 1200},
            "web_speech_api": {"language": "en-US", "continuous": False},
        },
    )

    assert response.status_code == 200
    data = response.json()["config"]
    assert data["asr_model"] == "web_speech_api"
    assert data["auto_send"] == {"enabled": True, "delay_ms": 1200}
    assert data["web_speech_api"]["language"] == "en-US"
    assert data["web_speech_api"]["continuous"] is False

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["asr_model"] == "web_speech_api"
    assert persisted["auto_send"]["delay_ms"] == 1200


def test_asr_config_store_preserves_raw_secret_placeholder_on_save(tmp_path: Path):
    config_path = tmp_path / "asr_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "asr_model: web_speech_api",
                "openai_whisper:",
                "  model: whisper-1",
                "  api_key: ${OPENAI_API_KEY}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    store = ASRConfigStore(
        {
            "asr_model": "web_speech_api",
            "openai_whisper": {
                "model": "whisper-1",
                "api_key": "resolved-runtime-key",
            },
        },
        path=config_path,
    )

    assert store.read()["openai_whisper"]["api_key"] == "resolved-runtime-key"

    store.update({"auto_send": {"enabled": True, "delay_ms": 1500}})

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["openai_whisper"]["api_key"] == "${OPENAI_API_KEY}"
    assert persisted["auto_send"] == {"enabled": True, "delay_ms": 1500}


def test_asr_config_store_does_not_rewrite_unpatched_secret_on_save(tmp_path: Path):
    config_path = tmp_path / "asr_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "asr_model: web_speech_api",
                "openai_whisper:",
                "  model: whisper-1",
                "  api_key: resolved-runtime-key",
                "",
            ]
        ),
        encoding="utf-8",
    )

    store = ASRConfigStore(path=config_path)

    store.update({"auto_send": {"enabled": False, "delay_ms": 1000}})

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["openai_whisper"]["api_key"] == "resolved-runtime-key"


def test_asr_config_store_patches_values_without_reformatting_yaml(tmp_path: Path):
    config_path = tmp_path / "asr_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "# keep header comment",
                "asr_model: web_speech_api # active provider",
                "auto_send:",
                "  enabled: false # writable",
                "  delay_ms: 2000",
                "web_speech_api:",
                "  language: 'zh-CN' # keep quote",
                "  continuous: true",
                "openai_whisper:",
                "  api_key: ${OPENAI_API_KEY}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    store = ASRConfigStore(path=config_path)

    store.update(
        {
            "asr_model": "web_speech_api",
            "auto_send": {"enabled": True, "delay_ms": 1200},
            "web_speech_api": {"language": "en-US"},
        }
    )

    updated = config_path.read_text(encoding="utf-8")
    assert "# keep header comment" in updated
    assert "asr_model: web_speech_api # active provider" in updated
    assert "  enabled: true # writable" in updated
    assert "  delay_ms: 1200" in updated
    assert "  language: 'en-US' # keep quote" in updated
    assert "  continuous: true" in updated
    assert "  api_key: ${OPENAI_API_KEY}" in updated


def test_asr_service_masks_secret_values_in_public_config(tmp_path: Path):
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "openai_whisper",
                "openai_whisper": {
                    "model": "whisper-1",
                    "api_key": "resolved-runtime-key",
                },
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    config = service.get_config()
    providers = service.list_providers()

    assert config["openai_whisper"]["api_key"] == "********"
    openai_provider = next(
        provider for provider in providers if provider["name"] == "openai_whisper"
    )
    assert openai_provider["config"]["api_key"] == "********"


def test_asr_service_ignores_masked_secret_patch(tmp_path: Path):
    config_path = tmp_path / "asr_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "asr_model: openai_whisper",
                "openai_whisper:",
                "  model: whisper-1",
                "  api_key: ${OPENAI_API_KEY}",
                "  base_url: ''",
                "",
            ]
        ),
        encoding="utf-8",
    )
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "openai_whisper",
                "openai_whisper": {
                    "model": "whisper-1",
                    "api_key": "resolved-runtime-key",
                    "base_url": "",
                },
            },
            path=config_path,
        )
    )

    service.update_config(
        {
            "openai_whisper": {
                "model": "gpt-4o-mini-transcribe",
                "api_key": "********",
            }
        }
    )

    raw_config = service.config_store.read()
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw_config["openai_whisper"]["api_key"] == "resolved-runtime-key"
    assert raw_config["openai_whisper"]["model"] == "whisper-1"
    assert persisted["openai_whisper"]["api_key"] == "${OPENAI_API_KEY}"
    assert persisted["openai_whisper"]["model"] == "whisper-1"


def test_asr_service_blocks_provider_write_protected_fields(tmp_path: Path):
    config_path = tmp_path / "asr_config.yaml"
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "faster_whisper",
                "faster_whisper": {
                    "model_path": "distil-large-v3",
                    "download_root": "models/whisper",
                    "language": "zh",
                },
                "whisper_cpp": {
                    "model_name": "small",
                    "model_dir": "models/whisper",
                },
                "openai_whisper": {
                    "model": "whisper-1",
                    "base_url": "",
                },
            },
            path=config_path,
        )
    )

    service.update_config(
        {
            "faster_whisper": {
                "model_path": "bad-model",
                "download_root": "bad-root",
                "language": "ja",
            },
            "whisper_cpp": {
                "model_name": "bad-model",
                "model_dir": "bad-dir",
            },
            "openai_whisper": {
                "model": "bad-model",
                "base_url": "https://bad.example/v1",
            },
        }
    )

    raw_config = service.config_store.read()
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw_config["faster_whisper"]["model_path"] == "distil-large-v3"
    assert raw_config["faster_whisper"]["download_root"] == "models/whisper"
    assert raw_config["faster_whisper"]["language"] == "ja"
    assert raw_config["whisper_cpp"]["model_name"] == "small"
    assert raw_config["whisper_cpp"]["model_dir"] == "models/whisper"
    assert raw_config["openai_whisper"]["model"] == "whisper-1"
    assert raw_config["openai_whisper"]["base_url"] == ""
    assert persisted["faster_whisper"]["model_path"] == "distil-large-v3"
    assert persisted["faster_whisper"]["download_root"] == "models/whisper"
    assert persisted["faster_whisper"]["language"] == "ja"
    assert persisted["whisper_cpp"]["model_name"] == "small"
    assert persisted["whisper_cpp"]["model_dir"] == "models/whisper"
    assert persisted["openai_whisper"]["model"] == "whisper-1"
    assert persisted["openai_whisper"]["base_url"] == ""


def test_asr_config_store_loads_backend_only_defaults(tmp_path: Path):
    store = ASRConfigStore(path=tmp_path / "asr_config.yaml")

    config = store.read()

    assert config["persistent_provider"] is True
    assert config["preload_provider"] is False


def test_asr_service_hides_and_rejects_backend_only_root_config(tmp_path: Path):
    config_path = tmp_path / "asr_config.yaml"
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "web_speech_api",
                "persistent_provider": True,
                "preload_provider": False,
                "auto_send": {"enabled": False},
            },
            path=config_path,
        )
    )

    public_config = service.get_config()
    assert "persistent_provider" not in public_config
    assert "preload_provider" not in public_config

    service.update_config(
        {
            "persistent_provider": False,
            "preload_provider": True,
            "auto_send": {"enabled": True},
        }
    )

    raw_config = service.config_store.read()
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw_config["persistent_provider"] is True
    assert raw_config["preload_provider"] is False
    assert raw_config["auto_send"]["enabled"] is True
    assert persisted["persistent_provider"] is True
    assert persisted["preload_provider"] is False


@pytest.mark.asyncio
async def test_asr_service_reuses_cached_local_provider_when_persistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _CountingASR("cached")
    create_provider = MagicMock(return_value=provider)
    monkeypatch.setattr("src.asr.service.ASRFactory.create", create_provider)
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "faster_whisper",
                "persistent_provider": True,
                "faster_whisper": {"language": "zh"},
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    first = await service.transcribe_audio(b"audio", provider="faster_whisper")
    second = await service.transcribe_audio(b"audio", provider="faster_whisper")

    assert first["text"] == "cached"
    assert second["text"] == "cached"
    assert provider.calls == 2
    assert create_provider.call_count == 1


@pytest.mark.asyncio
async def test_asr_service_creates_provider_per_request_when_not_persistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    first_provider = _CountingASR("first")
    second_provider = _CountingASR("second")
    create_provider = MagicMock(side_effect=[first_provider, second_provider])
    monkeypatch.setattr("src.asr.service.ASRFactory.create", create_provider)
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "faster_whisper",
                "persistent_provider": False,
                "faster_whisper": {"language": "zh"},
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    first = await service.transcribe_audio(b"audio", provider="faster_whisper")
    second = await service.transcribe_audio(b"audio", provider="faster_whisper")

    assert first["text"] == "first"
    assert second["text"] == "second"
    assert create_provider.call_count == 2


@pytest.mark.asyncio
async def test_asr_service_does_not_cache_cloud_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    first_provider = _CountingASR("first")
    second_provider = _CountingASR("second")
    create_provider = MagicMock(side_effect=[first_provider, second_provider])
    monkeypatch.setattr("src.asr.service.ASRFactory.create", create_provider)
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "openai_whisper",
                "persistent_provider": True,
                "openai_whisper": {"api_key": "test-key"},
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    first = await service.transcribe_audio(b"audio", provider="openai_whisper")
    second = await service.transcribe_audio(b"audio", provider="openai_whisper")

    assert first["text"] == "first"
    assert second["text"] == "second"
    assert create_provider.call_count == 2


@pytest.mark.asyncio
async def test_asr_service_clears_cache_after_provider_config_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    first_provider = _CountingASR("first")
    second_provider = _CountingASR("second")
    create_provider = MagicMock(side_effect=[first_provider, second_provider])
    monkeypatch.setattr("src.asr.service.ASRFactory.create", create_provider)
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "faster_whisper",
                "persistent_provider": True,
                "faster_whisper": {"language": "zh"},
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    first = await service.transcribe_audio(b"audio", provider="faster_whisper")
    service.update_config({"faster_whisper": {"language": "ja"}}, persist=False)
    second = await service.transcribe_audio(b"audio", provider="faster_whisper")

    assert first["text"] == "first"
    assert second["text"] == "second"
    assert create_provider.call_count == 2


@pytest.mark.asyncio
async def test_asr_service_clears_cache_after_provider_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    first_provider = _CountingASR("first")
    second_provider = _CountingASR("second")
    create_provider = MagicMock(side_effect=[first_provider, second_provider])
    monkeypatch.setattr("src.asr.service.ASRFactory.create", create_provider)
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "faster_whisper",
                "persistent_provider": True,
                "faster_whisper": {"language": "zh"},
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    first = await service.transcribe_audio(b"audio", provider="faster_whisper")
    service.switch_provider("faster_whisper", persist=False)
    second = await service.transcribe_audio(b"audio", provider="faster_whisper")

    assert first["text"] == "first"
    assert second["text"] == "second"
    assert create_provider.call_count == 2


@pytest.mark.asyncio
async def test_asr_service_serializes_cached_provider_transcription(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _CountingASR("cached", delay=0.01)
    create_provider = MagicMock(return_value=provider)
    monkeypatch.setattr("src.asr.service.ASRFactory.create", create_provider)
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "faster_whisper",
                "persistent_provider": True,
                "faster_whisper": {"language": "zh"},
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    await asyncio.gather(
        service.transcribe_audio(b"audio", provider="faster_whisper"),
        service.transcribe_audio(b"audio", provider="faster_whisper"),
    )

    assert provider.calls == 2
    assert provider.max_active_calls == 1
    assert create_provider.call_count == 1


@pytest.mark.asyncio
async def test_asr_service_preloads_active_persistent_local_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = _CountingASR("cached")
    create_provider = MagicMock(return_value=provider)
    monkeypatch.setattr("src.asr.service.ASRFactory.create", create_provider)
    service = ASRService(
        ASRConfigStore(
            {
                "asr_model": "faster_whisper",
                "persistent_provider": True,
                "preload_provider": True,
                "faster_whisper": {"language": "zh"},
            },
            path=tmp_path / "asr_config.yaml",
        )
    )

    await service.preload_active_provider()
    result = await service.transcribe_audio(b"audio", provider="faster_whisper")

    assert result["text"] == "cached"
    assert provider.preload_calls == 1
    assert provider.calls == 1
    assert create_provider.call_count == 1


@pytest.mark.asyncio
async def test_switch_asr_provider_rejects_unknown_provider(client_and_config_path):
    client, _config_path = client_and_config_path

    response = await client.post("/api/asr/switch", json={"provider": "unknown"})

    assert response.status_code == 400
    assert "Unknown ASR provider" in response.json()["detail"]


@pytest.mark.asyncio
async def test_web_speech_api_rejects_backend_transcription(client_and_config_path):
    client, _config_path = client_and_config_path

    response = await client.post(
        "/api/asr/transcribe",
        files={"audio": ("recording.wav", b"not-used", "audio/wav")},
    )

    assert response.status_code == 503
    assert "does not support backend transcription" in response.json()["detail"]


@pytest.mark.asyncio
async def test_transcribe_route_passes_upload_metadata_to_service(
    client_and_config_path,
):
    client, _config_path = client_and_config_path
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.asr_service.transcribe_audio = AsyncMock(  # type: ignore[attr-defined]
        return_value={"provider": "dummy", "text": "hello"}
    )

    response = await client.post(
        "/api/asr/transcribe",
        data={
            "source": "browser_recorder",
            "sample_rate": "16000",
            "channels": "1",
            "encoding": "pcm_s16le",
        },
        files={"audio": ("recording.wav", _build_pcm_wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 200
    await_args = app.state.asr_service.transcribe_audio.await_args  # type: ignore[attr-defined]
    kwargs = await_args.kwargs
    metadata = kwargs["upload_metadata"]
    assert isinstance(metadata, ASRAudioUploadMetadata)
    assert metadata.source == "browser_recorder"
    assert metadata.sample_rate == 16000
    assert metadata.channels == 1
    assert metadata.encoding == "pcm_s16le"


def test_default_wav_adapter_rejects_declared_contract_mismatch() -> None:
    audio = _build_pcm_wav_bytes(sample_rate=16000, channels=1)
    provider = _DummyASR()

    with pytest.raises(ASRTranscriptionError) as exc_info:
        provider.audio_bytes_to_float32_array(
            audio,
            filename="recording.wav",
            content_type="audio/wav",
            upload_metadata=ASRAudioUploadMetadata(
                source="browser_recorder",
                sample_rate=48000,
                channels=2,
                encoding="pcm_f32le",
            ),
        )

    message = str(exc_info.value)
    assert "Uploaded audio contract mismatch" in message
    assert "sample_rate declared 48000, actual 16000" in message
    assert "channels declared 2, actual 1" in message
    assert "encoding declared pcm_f32le, actual pcm_s16le" in message


@pytest.mark.asyncio
async def test_missing_optional_faster_whisper_dependency_returns_503(
    client_and_config_path,
    monkeypatch: pytest.MonkeyPatch,
):
    client, _config_path = client_and_config_path
    original_find_spec = faster_whisper_module.importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "faster_whisper":
            return None
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(faster_whisper_module.importlib.util, "find_spec", fake_find_spec)

    switch_response = await client.post("/api/asr/switch", json={"provider": "faster_whisper"})
    assert switch_response.status_code == 200

    response = await client.post(
        "/api/asr/transcribe",
        files={"audio": ("recording.wav", b"not-used", "audio/wav")},
    )

    assert response.status_code == 503
    assert "faster_whisper" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_optional_sherpa_onnx_dependency_returns_503(
    client_and_config_path,
    monkeypatch: pytest.MonkeyPatch,
):
    client, _config_path = client_and_config_path
    original_find_spec = sherpa_onnx_module.importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "sherpa_onnx":
            return None
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(sherpa_onnx_module.importlib.util, "find_spec", fake_find_spec)

    switch_response = await client.post("/api/asr/switch", json={"provider": "sherpa_onnx_asr"})
    assert switch_response.status_code == 200

    response = await client.post(
        "/api/asr/transcribe",
        files={"audio": ("recording.wav", b"not-used", "audio/wav")},
    )

    assert response.status_code == 503
    assert "sherpa_onnx" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_sherpa_onnx_model_returns_503(
    client_and_config_path,
    monkeypatch: pytest.MonkeyPatch,
):
    client, config_path = client_and_config_path
    original_find_spec = sherpa_onnx_module.importlib.util.find_spec
    config_path.write_text(
        "\n".join(
            [
                "asr_model: web_speech_api",
                "sherpa_onnx_asr:",
                "  model_type: sense_voice",
                "  sense_voice: models/missing-sense-voice/model.int8.onnx",
                "  tokens: models/missing-sense-voice/tokens.txt",
                "  num_threads: 4",
                "  use_itn: true",
                "  provider: cpu",
                "  debug: false",
                "",
            ]
        ),
        encoding="utf-8",
    )

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "sherpa_onnx":
            return object()
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(sherpa_onnx_module.importlib.util, "find_spec", fake_find_spec)

    switch_response = await client.post("/api/asr/switch", json={"provider": "sherpa_onnx_asr"})
    assert switch_response.status_code == 200

    response = await client.post(
        "/api/asr/transcribe",
        files={"audio": ("recording.wav", b"not-used", "audio/wav")},
    )

    assert response.status_code == 503
    assert "SenseVoice model not found" in response.json()["detail"]
