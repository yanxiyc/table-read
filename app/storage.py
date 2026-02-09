from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

from app.config import Settings
from app.models import Scene, SessionState, TranscriptEvent

logger = logging.getLogger(__name__)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def scene_dir(settings: Settings, scene_id: str) -> Path:
    path = settings.data_dir / scene_id
    _ensure_dir(path)
    return path


def scene_json_path(settings: Settings, scene_id: str) -> Path:
    return scene_dir(settings, scene_id) / "scene.json"


def session_json_path(settings: Settings, scene_id: str) -> Path:
    return scene_dir(settings, scene_id) / "session.json"


def transcript_jsonl_path(settings: Settings, scene_id: str) -> Path:
    return scene_dir(settings, scene_id) / "transcript.jsonl"


def audio_dir(settings: Settings, scene_id: str) -> Path:
    path = scene_dir(settings, scene_id) / "audio"
    _ensure_dir(path)
    return path


def save_scene(settings: Settings, scene: Scene) -> None:
    path = scene_json_path(settings, scene.scene_id)
    _ensure_dir(path.parent)
    path.write_text(
        json.dumps(scene.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def load_scene(settings: Settings, scene_id: str) -> Scene:
    """Load scene from disk (file-based fallback)."""
    path = scene_json_path(settings, scene_id)
    if not path.exists():
        raise FileNotFoundError(f"Scene '{scene_id}' not found.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scene.model_validate(data)


async def load_scene_smart(settings: Settings, scene_id: str) -> Scene:
    """Load scene from Notion first, falling back to local disk."""
    if settings.notion_token and settings.notion_database_id:
        try:
            from app.notion_client import load_scene_from_notion

            scene = await load_scene_from_notion(settings, scene_id)
            logger.info("Loaded scene %s from Notion", scene_id)
            return scene
        except Exception:
            logger.warning(
                "Failed to load scene %s from Notion, falling back to disk",
                scene_id,
                exc_info=True,
            )
    return load_scene(settings, scene_id)


def save_session(settings: Settings, scene_id: str, state: SessionState) -> None:
    path = session_json_path(settings, scene_id)
    _ensure_dir(path.parent)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def load_session(settings: Settings, scene_id: str) -> Optional[SessionState]:
    path = session_json_path(settings, scene_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionState.model_validate(data)


def append_transcript_event(
    settings: Settings, scene_id: str, event: TranscriptEvent
) -> None:
    path = transcript_jsonl_path(settings, scene_id)
    _ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
        fh.write("\n")


def save_locked_artifacts(
    settings: Settings, scene_id: str, locked_script_text: str, notes: Iterable[str]
) -> None:
    base = scene_dir(settings, scene_id)
    (base / "locked_script.txt").write_text(locked_script_text, encoding="utf-8")
    (base / "notes.json").write_text(
        json.dumps(list(notes), indent=2), encoding="utf-8"
    )
