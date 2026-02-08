from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.config import Settings
from app.models import Scene, SessionState

if TYPE_CHECKING:
    from livekit.agents import JobContext

    from app.agents.director_observer import DirectorObserver


@dataclass
class TableReadUserData:
    scene: Scene
    session_state: SessionState
    settings: Settings
    ctx: JobContext | None = None
    ai_voice_id: str = ""
    director: DirectorObserver | None = None
    evaluations: list[dict[str, Any]] = field(default_factory=list)
