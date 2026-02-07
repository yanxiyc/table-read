from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _parse_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cartesia_api_key: str
    cartesia_base_url: str
    cartesia_agent_id: str
    cartesia_tts_model: str
    cartesia_stt_model: str
    enable_cartesia: bool
    default_pace: float
    cartesia_tts_use_ssml_emotion: bool
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    _load_dotenv(base_dir / ".env")

    return Settings(
        data_dir=Path(os.getenv("SCENE_DATA_DIR", "data/scenes")),
        cartesia_api_key=os.getenv("CARTESIA_API_KEY", ""),
        cartesia_base_url=os.getenv("CARTESIA_BASE_URL", "https://api.cartesia.ai"),
        cartesia_agent_id=os.getenv("CARTESIA_AGENT_ID", ""),
        cartesia_tts_model=os.getenv("CARTESIA_TTS_MODEL", "sonic-3"),
        cartesia_stt_model=os.getenv("CARTESIA_STT_MODEL", "ink-whisper"),
        enable_cartesia=_parse_bool(os.getenv("ENABLE_CARTESIA", "true"), True),
        default_pace=float(os.getenv("DEFAULT_PACE", "1.0")),
        cartesia_tts_use_ssml_emotion=_parse_bool(
            os.getenv("CARTESIA_TTS_USE_SSML_EMOTION", "true"), True
        ),
        livekit_url=os.getenv("LIVEKIT_URL", ""),
        livekit_api_key=os.getenv("LIVEKIT_API_KEY", ""),
        livekit_api_secret=os.getenv("LIVEKIT_API_SECRET", ""),
    )
