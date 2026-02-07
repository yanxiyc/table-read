from __future__ import annotations

import time
from typing import Optional

import jwt

from app.config import Settings


class LiveKitTokenIssuer:
    def __init__(self, settings: Settings):
        self._settings = settings

    def create_room_token(
        self,
        room_name: str,
        identity: str,
        name: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> dict[str, str]:
        if not self._settings.livekit_url:
            raise RuntimeError("LIVEKIT_URL is not configured.")
        if not self._settings.livekit_api_key or not self._settings.livekit_api_secret:
            raise RuntimeError("LIVEKIT_API_KEY and LIVEKIT_API_SECRET are required.")

        now = int(time.time())
        payload = {
            "iss": self._settings.livekit_api_key,
            "sub": identity,
            "nbf": now - 5,
            "exp": now + ttl_seconds,
            "video": {
                "roomJoin": True,
                "room": room_name,
                "canPublish": True,
                "canSubscribe": True,
            },
        }
        if name:
            payload["name"] = name

        token = jwt.encode(
            payload,
            self._settings.livekit_api_secret,
            algorithm="HS256",
        )
        return {
            "url": self._settings.livekit_url,
            "token": token,
            "room": room_name,
            "identity": identity,
        }
