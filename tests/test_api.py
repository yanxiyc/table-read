from pathlib import Path

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
            json={"text": "I am here."},
        )
        assert actor_1.status_code == 200
        actor_state = actor_1.json()["state"]
        assert actor_state["beat_index"] == 3
        assert actor_state["current_speaker"] == "ACTOR"

        rewrite = client.post(
            f"/api/scenes/{scene_id}/utterance",
            json={"text": "reader try this: This isn't the place."},
        )
        assert rewrite.status_code == 200
        rewrite_state = rewrite.json()["state"]
        assert rewrite_state["beat_index"] == 3

        actor_2 = client.post(
            f"/api/scenes/{scene_id}/utterance",
            json={"text": "Fine. Here's the truth."},
        )
        assert actor_2.status_code == 200
        ready_state = actor_2.json()["state"]
        assert ready_state["status"] == "READY_TO_LOCK"

        lock = client.post(
            f"/api/scenes/{scene_id}/utterance",
            json={"text": "ok scene, lock this version"},
        )
        assert lock.status_code == 200
        lock_state = lock.json()["state"]
        assert lock_state["status"] == "LOCKED"
        assert "MOTHER: This isn't the place." in lock_state["locked_script_text"]
        assert "YOU: Fine. Here's the truth." in lock_state["locked_script_text"]

    get_settings.cache_clear()
