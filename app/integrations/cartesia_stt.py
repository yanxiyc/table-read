from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import urlencode

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

    def build_stream_url(
        self,
        language: str = "en",
        encoding: str = "pcm_s16le",
        sample_rate: int = 16000,
        min_volume: float = 0.01,
        max_silence_duration_secs: float = 0.45,
    ) -> str:
        if not self._settings.enable_cartesia:
            raise RuntimeError("Cartesia integration is disabled.")
        if not self._settings.cartesia_api_key:
            raise RuntimeError("CARTESIA_API_KEY is not configured.")

        base = self._settings.cartesia_base_url.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        else:
            ws_base = base

        query = urlencode(
            {
                "api_key": self._settings.cartesia_api_key,
                "cartesia_version": "2025-04-16",
                "model": self._settings.cartesia_stt_model,
                "language": language,
                "encoding": encoding,
                "sample_rate": sample_rate,
                "min_volume": min_volume,
                "max_silence_duration_secs": max_silence_duration_secs,
            }
        )
        return f"{ws_base}/stt/websocket?{query}"

    @staticmethod
    def decode_stream_message(raw: Any) -> Optional[dict[str, Any]]:
        if isinstance(raw, bytes):
            return None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"type": "unknown", "raw": raw}
            if isinstance(parsed, dict):
                return parsed
            return {"type": "unknown", "raw": parsed}
        if isinstance(raw, dict):
            return raw
        return None

    @staticmethod
    def extract_transcript_text(message: dict[str, Any]) -> str:
        text = message.get("text")
        if isinstance(text, str):
            return text.strip()

        transcript = message.get("transcript")
        if isinstance(transcript, str):
            return transcript.strip()
        if isinstance(transcript, dict):
            nested = transcript.get("text") or transcript.get("transcript")
            if isinstance(nested, str):
                return nested.strip()

        alts = message.get("alternatives")
        if isinstance(alts, list) and alts:
            first = alts[0]
            if isinstance(first, dict):
                alt_text = first.get("text") or first.get("transcript")
                if isinstance(alt_text, str):
                    return alt_text.strip()

        return ""

    @staticmethod
    def is_final_transcript(message: dict[str, Any]) -> bool:
        for key in ("is_final", "final", "done", "utterance_done", "end_of_utterance"):
            value = message.get(key)
            if isinstance(value, bool):
                return value

        transcript = message.get("transcript")
        if isinstance(transcript, dict):
            for key in ("is_final", "final"):
                value = transcript.get(key)
                if isinstance(value, bool):
                    return value

        # Default to final when no explicit partial/final flag is provided.
        return True
