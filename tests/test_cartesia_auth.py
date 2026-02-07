from pathlib import Path

import httpx

from app.config import Settings
from app.integrations.cartesia_auth import CartesiaAgentAuthClient


def _settings() -> Settings:
    return Settings(
        data_dir=Path("data/scenes"),
        cartesia_api_key="test_api_key",
        cartesia_base_url="https://api.cartesia.ai",
        cartesia_agent_id="agent_123",
        cartesia_tts_model="sonic-3",
        cartesia_stt_model="ink-whisper",
        enable_cartesia=True,
        default_pace=1.0,
        cartesia_tts_use_ssml_emotion=True,
        livekit_url="",
        livekit_api_key="",
        livekit_api_secret="",
    )


def test_create_access_token_accepts_token_field(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"token": "agent_token_abc"}

    def fake_post(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    client = CartesiaAgentAuthClient(_settings())
    token = client.create_access_token()
    assert token == "agent_token_abc"


def test_build_stream_url_uses_agent_id_and_token():
    client = CartesiaAgentAuthClient(_settings())
    ws_url = client.build_stream_url("agent_token_abc")
    assert ws_url.startswith("wss://api.cartesia.ai/agents/stream/agent_123?")
    assert "access_token=agent_token_abc" in ws_url
    assert "cartesia_version=2025-04-16" in ws_url
