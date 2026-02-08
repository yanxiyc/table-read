from __future__ import annotations

from app.models import StyleState


def clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def emotion_from_style(style: StyleState) -> str:
    """Map style parameters to a Cartesia emotion label."""
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
