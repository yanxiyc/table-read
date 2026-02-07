from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from app.config import Settings
from app.models import StyleState
from app.storage.files import audio_dir


class CartesiaTTSClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    def speak(
        self, scene_id: str, event_id: str, text: str, voice_id: str, style: StyleState
    ) -> Optional[str]:
        if not text.strip():
            return None
        if not self._settings.enable_cartesia:
            return None
        if not self._settings.cartesia_api_key:
            raise RuntimeError("CARTESIA_API_KEY is not configured.")

        url = f"{self._settings.cartesia_base_url}/tts/bytes"
        headers = {
            "X-API-Key": self._settings.cartesia_api_key,
            "Cartesia-Version": "2025-04-16",
            "Content-Type": "application/json",
        }
        emotion = self._emotion_from_style(style)
        transcript = self._apply_expression_tag(text, emotion, style.pace)
        payload = {
            "model_id": self._settings.cartesia_tts_model,
            "transcript": transcript,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {
                "container": "wav",
                "encoding": "pcm_f32le",
                "sample_rate": 44100,
            },
            "generation_config": {
                "speed": round(_clamp(style.pace, 0.7, 1.3), 2),
                "emotion": emotion,
            },
            "language": "en",
        }

        response = httpx.post(url, headers=headers, json=payload, timeout=45.0)
        response.raise_for_status()

        target_path = Path(audio_dir(self._settings, scene_id)) / f"{event_id}.wav"
        target_path.write_bytes(response.content)
        return f"/api/scenes/{scene_id}/audio/{event_id}.wav"

    def _emotion_from_style(self, style: StyleState) -> str:
        if style.tension >= 0.75 and style.warmth <= -0.2:
            return "angry"
        if style.tension >= 0.75 and style.warmth > -0.2:
            return "scared"
        if style.warmth >= 0.5 and style.tension < 0.6:
            return "content"
        if style.warmth >= 0.2 and style.tension >= 0.55:
            return "excited"
        if style.warmth <= -0.5:
            return "sad"
        return "neutral"

    def _apply_expression_tag(self, text: str, emotion: str, pace: float) -> str:
        if not self._settings.cartesia_tts_use_ssml_emotion:
            return text
        speed = round(_clamp(pace, 0.6, 1.5), 2)
        return f'<emotion value="{emotion}" /><speed ratio="{speed}"/>{text}'


def _clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))
