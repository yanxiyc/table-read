"""Notion API client for scene persistence.

Uses httpx to call the Notion REST API directly.
Scenes are stored as database pages with beats in a code-block child.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import Settings
from app.models import Beat, Scene, Variant

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _rich_text_plain(rich_text: list[dict[str, Any]]) -> str:
    """Extract plain text from a Notion rich_text array."""
    return "".join(item.get("plain_text", "") for item in rich_text)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


async def load_scene_from_notion(settings: Settings, scene_id: str) -> Scene:
    """Query the Notion database for a scene by Scene ID, then parse it.

    Reads page properties for metadata and page children for the beats
    JSON code block.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        # Query database for matching Scene ID
        resp = await client.post(
            f"{NOTION_API}/databases/{settings.notion_database_id}/query",
            headers=_headers(settings),
            json={
                "filter": {
                    "property": "Scene ID",
                    "rich_text": {"equals": scene_id},
                },
                "page_size": 1,
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if not results:
            raise FileNotFoundError(
                f"Scene '{scene_id}' not found in Notion database."
            )

        page = results[0]
        page_id = page["id"]
        props = page["properties"]

        title = _rich_text_plain(props["Name"]["title"])
        ai_character = _rich_text_plain(props["AI Character"]["rich_text"])
        actor_label = _rich_text_plain(props["Actor Label"]["rich_text"])
        voice_id = _rich_text_plain(props["Voice ID"]["rich_text"])

        # Read page children to find the beats code block
        children_resp = await client.get(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=_headers(settings),
        )
        children_resp.raise_for_status()
        blocks = children_resp.json().get("results", [])

        beats: list[Beat] = []
        for block in blocks:
            if block.get("type") != "code":
                continue
            code = block["code"]
            caption = "".join(
                c.get("plain_text", "") for c in code.get("caption", [])
            ).lower()
            if caption == "beats":
                beats_json = _rich_text_plain(code.get("rich_text", []))
                raw_beats = json.loads(beats_json)
                beats = [_parse_beat(b) for b in raw_beats]
                break

    return Scene(
        scene_id=scene_id,
        title=title,
        characters={"AI": ai_character, "ACTOR": actor_label},
        voice={"ai_voice_id": voice_id},
        beats=beats,
    )


def _parse_beat(data: dict[str, Any]) -> Beat:
    """Parse a beat dict from Notion JSON into a Beat model."""
    variants = [
        Variant(
            id=v.get("id", ""),
            text=v.get("text", ""),
            source=v.get("source", "manual"),
        )
        for v in data.get("variants", [])
    ]
    return Beat(
        id=data["id"],
        speaker=data["speaker"],
        character=data.get("character", ""),
        canonical=data.get("canonical"),
        variants=variants,
        active_variant_id=data.get("active_variant_id"),
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def update_scene_status_in_notion(
    settings: Settings, scene_id: str, status: str
) -> None:
    """Update the Status select property of a scene page in Notion."""
    page_id = await _find_page_id(settings, scene_id)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=_headers(settings),
            json={
                "properties": {
                    "Status": {"select": {"name": status}},
                }
            },
        )
        resp.raise_for_status()

    logger.info("Updated Notion scene %s status to %s", scene_id, status)


async def append_director_notes_in_notion(
    settings: Settings, scene_id: str, notes: list[str]
) -> None:
    """Append director evaluation notes as a callout block to the scene page."""
    page_id = await _find_page_id(settings, scene_id)

    content = "\n".join(f"• {n}" for n in notes)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=_headers(settings),
            json={
                "children": [
                    {
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "icon": {"type": "emoji", "emoji": "🎬"},
                            "rich_text": [
                                {"text": {"content": content[:2000]}},
                            ],
                        },
                    }
                ]
            },
        )
        resp.raise_for_status()

    logger.info("Appended director notes to Notion scene %s", scene_id)


# ---------------------------------------------------------------------------
# Create (for migration / testing)
# ---------------------------------------------------------------------------


async def create_scene_in_notion(settings: Settings, scene: Scene) -> None:
    """Create a new scene page in the Notion database."""
    ai_character = scene.characters.get("AI", "")
    actor_label = scene.characters.get("ACTOR", "")
    voice_id = scene.voice.get("ai_voice_id", "")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{NOTION_API}/pages",
            headers=_headers(settings),
            json={
                "parent": {"database_id": settings.notion_database_id},
                "properties": {
                    "Name": {
                        "title": [{"text": {"content": scene.title}}]
                    },
                    "Scene ID": {
                        "rich_text": [{"text": {"content": scene.scene_id}}]
                    },
                    "AI Character": {
                        "rich_text": [{"text": {"content": ai_character}}]
                    },
                    "Actor Label": {
                        "rich_text": [{"text": {"content": actor_label}}]
                    },
                    "Voice ID": {
                        "rich_text": [{"text": {"content": voice_id}}]
                    },
                    "Status": {"select": {"name": "IDLE"}},
                },
                "children": [
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [
                                {
                                    "text": {
                                        "content": json.dumps(
                                            [
                                                b.model_dump(mode="json")
                                                for b in scene.beats
                                            ],
                                            indent=2,
                                        )
                                    }
                                }
                            ],
                            "language": "json",
                            "caption": [{"text": {"content": "beats"}}],
                        },
                    }
                ],
            },
        )
        resp.raise_for_status()

    logger.info("Created scene %s in Notion", scene.scene_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _find_page_id(settings: Settings, scene_id: str) -> str:
    """Find the Notion page ID for a given scene_id."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{NOTION_API}/databases/{settings.notion_database_id}/query",
            headers=_headers(settings),
            json={
                "filter": {
                    "property": "Scene ID",
                    "rich_text": {"equals": scene_id},
                },
                "page_size": 1,
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

    if not results:
        raise FileNotFoundError(
            f"Scene '{scene_id}' not found in Notion database."
        )
    return results[0]["id"]
