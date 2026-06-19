from __future__ import annotations

from src.app import create_app
from src.vad import VADService


def test_create_app_initializes_vad_service() -> None:
    app = create_app(
        {
            "server": {"cors": {"enabled": False}},
            "asr": {},
            "tts": {},
            "vad": {
                "enabled": True,
                "vad_model": "fake",
                "fake": {
                    "required_hits": 2,
                },
            },
            "auth": {"enabled": False},
        }
    )

    assert isinstance(app.state.vad_service, VADService)
    assert app.state.vad_service.get_config()["enabled"] is True
    assert app.state.vad_service.get_config()["vad_model"] == "fake"
