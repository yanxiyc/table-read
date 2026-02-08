from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _parse_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cartesia_api_key: str
    cartesia_base_url: str
    cartesia_tts_model: str
    enable_cartesia: bool
    default_pace: float
    cartesia_tts_use_ssml_emotion: bool
    cors_origins: list[str]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env", override=False)

    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    cors_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    return Settings(
        data_dir=Path(os.getenv("SCENE_DATA_DIR", "data/scenes")),
        cartesia_api_key=os.getenv("CARTESIA_API_KEY", ""),
        cartesia_base_url=os.getenv("CARTESIA_BASE_URL", "https://api.cartesia.ai"),
        cartesia_tts_model=os.getenv("CARTESIA_TTS_MODEL", "sonic-3"),
        enable_cartesia=_parse_bool(os.getenv("ENABLE_CARTESIA", "true"), True),
        default_pace=float(os.getenv("DEFAULT_PACE", "1.0")),
        cartesia_tts_use_ssml_emotion=_parse_bool(
            os.getenv("CARTESIA_TTS_USE_SSML_EMOTION", "true"), True
        ),
        cors_origins=cors_origins,
    )
