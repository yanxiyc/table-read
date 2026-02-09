from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    default_pace: float
    notion_token: str
    notion_database_id: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env", override=False)

    return Settings(
        data_dir=Path(os.getenv("SCENE_DATA_DIR", "data/scenes")),
        default_pace=float(os.getenv("DEFAULT_PACE", "1.0")),
        notion_token=os.getenv("NOTION_TOKEN", ""),
        notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
    )
