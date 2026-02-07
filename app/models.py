from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_event_id() -> str:
    return uuid4().hex


class SceneStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    READY_TO_LOCK = "READY_TO_LOCK"
    LOCKING = "LOCKING"
    LOCKED = "LOCKED"


class Variant(BaseModel):
    id: str
    text: str
    source: str = "manual"


class Beat(BaseModel):
    id: str
    speaker: Literal["AI", "ACTOR"]
    character: str = ""
    canonical: Optional[str] = None
    variants: list[Variant] = Field(default_factory=list)
    active_variant_id: Optional[str] = None


class Scene(BaseModel):
    scene_id: str
    title: str
    characters: dict[str, str]
    voice: dict[str, str]
    beats: list[Beat]


class StyleState(BaseModel):
    tension: float = 0.5
    warmth: float = 0.0
    pace: float = 1.0
    pause_ms: int = 350


class TranscriptEvent(BaseModel):
    event_id: str = Field(default_factory=new_event_id)
    ts: str = Field(default_factory=utc_now_iso)
    speaker: Literal["AI", "ACTOR", "DIRECTOR", "SYSTEM", "UNKNOWN"]
    text: str
    meta: dict[str, Any] = Field(default_factory=dict)


class DirectorEvent(BaseModel):
    ts: str = Field(default_factory=utc_now_iso)
    cmd: str
    target_beat_id: Optional[str] = None
    applied: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class SessionState(BaseModel):
    status: SceneStatus = SceneStatus.IDLE
    beat_index: int = 0
    last_talk_turn: Optional[Literal["AI", "ACTOR"]] = None
    style: StyleState = Field(default_factory=StyleState)
    transcript: list[TranscriptEvent] = Field(default_factory=list)
    director_events: list[DirectorEvent] = Field(default_factory=list)
    locked_script_text: Optional[str] = None
    actor_latest_takes: dict[str, str] = Field(default_factory=dict)
    locked_notes: Optional[list[str]] = None


class CreateSceneRequest(BaseModel):
    title: str
    script_text: str
    ai_character_name: str = "AI"
    ai_voice_id: str


class CreateSceneResponse(BaseModel):
    scene_id: str


class StateResponse(BaseModel):
    scene_id: str
    status: SceneStatus
    beat_index: int
    current_beat_id: Optional[str]
    current_speaker: Optional[Literal["AI", "ACTOR"]]
    transcript: list[TranscriptEvent]
    director_events: list[DirectorEvent]
    locked_script_text: Optional[str]
    locked_notes: Optional[list[str]]
    style: StyleState
