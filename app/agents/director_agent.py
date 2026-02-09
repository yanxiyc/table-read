"""Standalone Director Agent that joins a LiveKit room as a real-time observer.

Subscribes to the actor's audio via STT, evaluates each delivery using Claude,
and sends feedback to the frontend via RPC. Runs as a separate participant
in the room alongside the character agent.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from livekit.agents import RunContext
from livekit.agents.llm import ChatContext, ChatMessage, function_tool
from livekit.agents.voice import Agent

from app.agents.rpc import send_rpc_to_ui_safe
from app.config import Settings
from app.models import Beat, Scene

logger = logging.getLogger(__name__)

# Load evaluation prompt template
_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "director_evaluation.yaml"


def _load_prompt_template() -> str:
    if _PROMPT_PATH.exists():
        data = yaml.safe_load(_PROMPT_PATH.read_text())
        return data.get("system_prompt", "")
    return ""


@dataclass
class DirectorUserData:
    scene: Scene
    settings: Settings
    actor_beats: list[Beat] = field(default_factory=list)
    eval_history: list[dict[str, Any]] = field(default_factory=list)
    consecutive_narrating: int = 0
    ctx: Any | None = None
    # Synced from character agent via beat_update RPC
    last_known_beat_index: int = 0
    last_actor_beat_id: str | None = None


class DirectorAgent(Agent):
    """LiveKit Agent that observes actor performance in real-time.

    Joins the room as a separate participant, subscribes to the actor's
    audio, transcribes it via STT, and evaluates each utterance with Claude.
    """

    instructions: str = (
        "You are an expert acting coach and theater director observing a "
        "table-read rehearsal. You listen to the actor's delivery and provide "
        "real-time feedback on whether they are truly ACTING (emotionally "
        "engaged, making choices) or merely READING (flat, monotone). "
        "Be encouraging but honest. Give specific, actionable notes. "
        "You do NOT voice any character lines — you only observe and evaluate."
    )

    def __init__(self):
        self._prompt_template = _load_prompt_template()
        super().__init__(instructions=self.instructions)

    async def on_enter(self) -> None:
        """Called when the director agent session starts."""
        ud: DirectorUserData = self.session.userdata
        logger.info(
            "Director agent observing scene %s (%d beats)",
            ud.scene.scene_id,
            len(ud.scene.beats),
        )
        ud.actor_beats = [b for b in ud.scene.beats if b.speaker == "ACTOR"]

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """Evaluate every actor utterance heard in the room."""
        text = new_message.text_content or ""
        if not text.strip():
            return

        ud: DirectorUserData = self.session.userdata

        if not ud.actor_beats:
            return

        # Derive actor beat from the character agent's beat_index
        # (synced via beat_update RPC) rather than a blind counter,
        # so rewinds are handled correctly.
        beat = self._current_actor_beat(ud)
        if beat is None:
            return

        evaluation = await self._evaluate(beat, text, ud)
        if evaluation is None:
            return

        # Track consecutive narrating
        if evaluation.get("is_narrating", False):
            ud.consecutive_narrating += 1
        else:
            ud.consecutive_narrating = 0

        ud.eval_history.append(evaluation)

        # Send feedback to frontend via RPC
        await self._send_feedback(evaluation, ud)

        # Speak feedback if warranted (only when TTS is available)
        if evaluation.get("should_speak_feedback", False) and self.session.tts:
            note = evaluation.get("director_note", "")
            if note:
                await self.session.say(
                    f"Director note: {note}",
                    allow_interruptions=True,
                )

    async def _evaluate(
        self, beat: Beat, actor_text: str, ud: DirectorUserData
    ) -> dict[str, Any] | None:
        """Call Claude to evaluate the actor's delivery."""
        try:
            expected = beat.canonical or ""
            character = beat.character or "ACTOR"

            previous_feedback = ""
            if ud.eval_history:
                last_evals = ud.eval_history[-3:]
                previous_feedback = "\n".join(
                    f"- Beat {e.get('beat_id', '?')}: {e.get('verdict', '?')} "
                    f"- {e.get('director_note', '')}"
                    for e in last_evals
                )

            user_prompt = (
                f"Character: {character}\n"
                f"Expected line: {expected}\n"
                f"Actor said: {actor_text}\n"
                f"Consecutive 'narrating' verdicts: {ud.consecutive_narrating}\n"
            )
            if previous_feedback:
                user_prompt += f"\nPrevious feedback:\n{previous_feedback}\n"

            user_prompt += (
                "\nEvaluate the actor's delivery. Return JSON with these fields:\n"
                '{"is_acting": bool, "is_narrating": bool, '
                '"emotional_engagement": "low"|"medium"|"high", '
                '"overall_rating": 1-10, "director_note": "brief constructive note", '
                '"should_speak_feedback": bool}\n'
            )

            chat_ctx = ChatContext()
            system_prompt = self._prompt_template or (
                "You are an expert acting coach and theater director. "
                "Evaluate whether an actor is truly ACTING (emotionally engaged, "
                "making choices, inhabiting the character) or merely NARRATING/READING "
                "(monotone, flat, just saying words without feeling). "
                "Be encouraging but honest. Give specific, actionable feedback. "
                "Return valid JSON only."
            )
            chat_ctx.add_message(role="system", content=system_prompt)
            chat_ctx.add_message(role="user", content=user_prompt)

            # Use the session's LLM (Claude via inference API)
            stream = self.session.llm.chat(chat_ctx=chat_ctx)
            response_text = ""
            async for chunk in stream:
                try:
                    if chunk.delta and chunk.delta.content:
                        response_text += chunk.delta.content
                except Exception:
                    continue

            if not response_text.strip():
                logger.warning("Director LLM returned empty response")
                return None

            evaluation = self._parse_json(response_text)
            if evaluation is None:
                logger.warning("Failed to parse evaluation: %s", response_text[:200])
                return None

            evaluation["beat_id"] = beat.id
            evaluation["actor_text"] = actor_text
            return evaluation

        except Exception:
            logger.exception("Director evaluation failed")
            return None

    async def _send_feedback(
        self, evaluation: dict[str, Any], ud: DirectorUserData
    ) -> None:
        """Send director feedback to frontend via RPC."""
        ctx = ud.ctx
        if not ctx:
            logger.debug("No JobContext available; skipping director_feedback RPC")
            return

        payload = {
            "beat_id": evaluation.get("beat_id", ""),
            "is_acting": evaluation.get("is_acting", False),
            "is_narrating": evaluation.get("is_narrating", True),
            "emotional_engagement": evaluation.get("emotional_engagement", "low"),
            "overall_rating": evaluation.get("overall_rating", 5),
            "director_note": evaluation.get("director_note", ""),
            "consecutive_narrating": ud.consecutive_narrating,
        }

        await send_rpc_to_ui_safe(ctx, "director_feedback", payload)

    # ------------------------------------------------------------------
    # Beat-index helpers
    # ------------------------------------------------------------------

    def _current_actor_beat(self, ud: DirectorUserData) -> Beat | None:
        """Pick the best actor beat for evaluation.

        Prefer the last actor beat id from beat_update RPC to avoid
        off-by-one when beat_index advances after an actor line.
        Fallback to deriving from beat_index.
        """
        if ud.last_actor_beat_id:
            for beat in ud.actor_beats:
                if beat.id == ud.last_actor_beat_id:
                    return beat

        global_idx = ud.last_known_beat_index
        actor_idx = sum(
            1
            for b in ud.scene.beats[:global_idx]
            if b.speaker == "ACTOR"
        )
        if not ud.actor_beats:
            return None
        return ud.actor_beats[min(actor_idx, len(ud.actor_beats) - 1)]

    # ------------------------------------------------------------------
    # Notion tools (callable by the LLM)
    # ------------------------------------------------------------------

    @function_tool
    async def update_scene_status(
        self, context: RunContext, status: str
    ) -> str:
        """Update the scene status in Notion.

        Args:
            status: New status value. One of: IDLE, RUNNING, READY_TO_LOCK, LOCKED
        """
        ud: DirectorUserData = self.session.userdata
        if not ud.settings.notion_token:
            return "Notion not configured."
        try:
            from app.notion_client import update_scene_status_in_notion

            await update_scene_status_in_notion(
                ud.settings, ud.scene.scene_id, status
            )
            return f"Scene status updated to {status}."
        except Exception as exc:
            logger.exception("Failed to update scene status in Notion")
            return f"Failed: {exc}"

    @function_tool
    async def save_director_notes(
        self, context: RunContext, notes: str
    ) -> str:
        """Save director evaluation notes to the Notion scene page.

        Args:
            notes: Director evaluation summary to append to the scene page.
        """
        ud: DirectorUserData = self.session.userdata
        if not ud.settings.notion_token:
            return "Notion not configured."
        try:
            from app.notion_client import append_director_notes_in_notion

            await append_director_notes_in_notion(
                ud.settings,
                ud.scene.scene_id,
                notes.split("\n"),
            )
            return "Director notes saved to Notion."
        except Exception as exc:
            logger.exception("Failed to save director notes to Notion")
            return f"Failed: {exc}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        """Extract JSON from LLM response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None
