from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.config import Settings


class CartesiaAgentAuthClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    def create_access_token(self, expires_in_seconds: int = 1800) -> str:
        if not self._settings.cartesia_api_key:
            raise RuntimeError("CARTESIA_API_KEY is not configured.")

        url = f"{self._settings.cartesia_base_url.rstrip('/')}/access-token"
        headers = {
            "Authorization": f"Bearer {self._settings.cartesia_api_key}",
            "Cartesia-Version": "2025-04-16",
            "Content-Type": "application/json",
        }
        payload = {
            "expires_in": expires_in_seconds,
            "grants": {"agent": True},
        }
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise RuntimeError("Cartesia access-token response did not include token.")
        return str(token)

    def build_stream_url(self, access_token: str) -> str:
        if not self._settings.cartesia_agent_id:
            raise RuntimeError("CARTESIA_AGENT_ID is not configured.")

        base = self._settings.cartesia_base_url.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        else:
            ws_base = base

        query = urlencode({"access_token": access_token, "cartesia_version": "2025-04-16"})
        return f"{ws_base}/agents/stream/{self._settings.cartesia_agent_id}?{query}"
