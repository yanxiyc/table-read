from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _create_scene(client: TestClient) -> str:
    payload = {
        "title": "kitchen_tense",
        "script_text": "MOTHER: You're late.\nYOU:\nMOTHER: Fine. Say it.\nYOU:\n",
        "ai_character_name": "MOTHER",
        "ai_voice_id": "voice-123",
    }
    response = client.post("/api/scenes", json=payload)
    assert response.status_code == 200
    return response.json()["scene_id"]


def test_scene_runtime_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCENE_DATA_DIR", str(tmp_path / "scenes"))
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_AGENT_ID", "")
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        scene_id = _create_scene(client)

        start = client.post(f"/api/scenes/{scene_id}/start")
        assert start.status_code == 200
        start_state = start.json()["state"]
        assert start_state["status"] == "RUNNING"
        assert start_state["beat_index"] == 1
        assert start_state["current_speaker"] == "ACTOR"

        actor_1 = client.post(
            f"/api/scenes/{scene_id}/utterance",
            data={"text_override": "I am here."},
        )
        assert actor_1.status_code == 200
        actor_state = actor_1.json()["state"]
        assert actor_state["beat_index"] == 3
        assert actor_state["current_speaker"] == "ACTOR"

        rewrite = client.post(
            f"/api/scenes/{scene_id}/utterance",
            data={"text_override": "reader try this: This isn't the place."},
        )
        assert rewrite.status_code == 200
        rewrite_state = rewrite.json()["state"]
        assert rewrite_state["beat_index"] == 3

        actor_2 = client.post(
            f"/api/scenes/{scene_id}/utterance",
            data={"text_override": "Fine. Here's the truth."},
        )
        assert actor_2.status_code == 200
        ready_state = actor_2.json()["state"]
        assert ready_state["status"] == "READY_TO_LOCK"

        end = client.post(f"/api/scenes/{scene_id}/end")
        assert end.status_code == 200
        lock_state = end.json()["state"]
        assert lock_state["status"] == "LOCKED"
        assert "MOTHER: This isn't the place." in lock_state["locked_script_text"]
        assert "YOU: Fine. Here's the truth." in lock_state["locked_script_text"]

    get_settings.cache_clear()


def test_scene_runtime_start_in_agent_mode_does_not_auto_advance_ai(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCENE_DATA_DIR", str(tmp_path / "scenes"))
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_AGENT_ID", "agent_test_123")
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        scene_id = _create_scene(client)
        start = client.post(f"/api/scenes/{scene_id}/start")
        assert start.status_code == 200
        state = start.json()["state"]
        assert state["status"] == "RUNNING"
        assert state["beat_index"] == 0
        assert state["current_speaker"] == "AI"

    get_settings.cache_clear()


def test_end_scene_endpoint_from_running(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCENE_DATA_DIR", str(tmp_path / "scenes"))
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_AGENT_ID", "")
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        scene_id = _create_scene(client)
        start = client.post(f"/api/scenes/{scene_id}/start")
        assert start.status_code == 200
        end = client.post(f"/api/scenes/{scene_id}/end")
        assert end.status_code == 200
        assert end.json()["state"]["status"] == "LOCKED"

    get_settings.cache_clear()


def test_agent_session_requires_agent_id(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCENE_DATA_DIR", str(tmp_path / "scenes"))
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_AGENT_ID", "")
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        scene_id = _create_scene(client)
        response = client.get(f"/api/scenes/{scene_id}/agent-session")
        assert response.status_code == 400

    get_settings.cache_clear()


def test_agent_session_returns_ws_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCENE_DATA_DIR", str(tmp_path / "scenes"))
    monkeypatch.setenv("ENABLE_CARTESIA", "true")
    monkeypatch.setenv("CARTESIA_BASE_URL", "https://api.cartesia.ai")
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia_test_key")
    monkeypatch.setenv("CARTESIA_AGENT_ID", "agent_test_456")
    get_settings.cache_clear()
    app = create_app()
    app.state.cartesia_auth.create_access_token = lambda expires_in_seconds=1800: "token_test_abc"

    with TestClient(app) as client:
        scene_id = _create_scene(client)
        response = client.get(f"/api/scenes/{scene_id}/agent-session")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent_test_456"
        assert data["input_format"] == "pcm_16000"
        assert "/agents/stream/agent_test_456?" in data["ws_url"]
        assert "access_token=token_test_abc" in data["ws_url"]
        assert "cartesia_version=2025-04-16" in data["ws_url"]

    get_settings.cache_clear()


def test_livekit_token_requires_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCENE_DATA_DIR", str(tmp_path / "scenes"))
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_AGENT_ID", "")
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        scene_id = _create_scene(client)
        response = client.get(f"/api/scenes/{scene_id}/livekit-token")
        assert response.status_code == 400

    get_settings.cache_clear()


def test_livekit_token_issued_with_claims(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCENE_DATA_DIR", str(tmp_path / "scenes"))
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_AGENT_ID", "")
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "lk_test_key")
    secret = "lk_test_secret_with_recommended_length_32"
    monkeypatch.setenv("LIVEKIT_API_SECRET", secret)
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        scene_id = _create_scene(client)
        response = client.get(f"/api/scenes/{scene_id}/livekit-token")
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "wss://example.livekit.cloud"
        decoded = jwt.decode(
            data["token"],
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        assert decoded["iss"] == "lk_test_key"
        assert decoded["video"]["room"] == f"table-read-{scene_id}"
        assert decoded["video"]["roomJoin"] is True

    get_settings.cache_clear()
