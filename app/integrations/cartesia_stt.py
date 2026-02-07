from __future__ import annotations

import httpx

from app.config import Settings


class CartesiaSTTClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    def transcribe_utterance(self, audio_bytes: bytes, mime_type: str, filename: str = "utterance.wav") -> str:
        if not audio_bytes:
            return ""
        if not self._settings.enable_cartesia:
            return ""
        if not self._settings.cartesia_api_key:
            raise RuntimeError("CARTESIA_API_KEY is not configured.")

        url = f"{self._settings.cartesia_base_url}/stt"
        headers = {
            "X-API-Key": self._settings.cartesia_api_key,
            "Cartesia-Version": "2025-04-16",
        }
        files = {"file": (filename, audio_bytes, mime_type or "audio/wav")}
        data = {"model": self._settings.cartesia_stt_model}

        response = httpx.post(url, headers=headers, files=files, data=data, timeout=60.0)
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("text", "")).strip()
