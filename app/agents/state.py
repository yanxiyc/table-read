from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import Settings
from app.models import Scene, SessionState

if TYPE_CHECKING:
    from livekit.agents import JobContext


@dataclass
class TableReadUserData:
    scene: Scene
    session_state: SessionState
    settings: Settings
    ctx: JobContext | None = None
    ai_voice_id: str = ""
