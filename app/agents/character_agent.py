from __future__ import annotations

import asyncio
import logging
from typing import Any

from livekit.agents.voice import Agent, UserTurnCompleted

from app.agents.state import TableReadUserData
from app.models import (
    Beat,
    DirectorEvent,
    SceneStatus,
    SessionState,
    TranscriptEvent,
)
from app.runtime.commands import apply_director_command, classify_utterance
from app.agents.rpc import send_rpc_to_ui_safe, stream_bytes_to_ui
from app.style_utils import emotion_from_style
from app.storage import (
    append_transcript_event,
    save_locked_artifacts,
    save_scene,
    save_session,
)

logger = logging.getLogger(__name__)


class ScriptedCharacterAgent(Agent):
    """LiveKit voice agent that manages a table-read rehearsal beat loop.

    The agent walks through a scripted scene beat by beat, voicing AI
    character lines and waiting for the human actor to deliver theirs.
    Director commands and lock requests are also handled inline.
    """

    instructions: str = (
        "You are a table-read rehearsal partner. You voice the AI character's "
        "lines in the script, wait for the actor to deliver theirs, and respond "
        "to director commands such as pace or emotion changes. When all beats "
        "are complete the actor may lock the scene."
    )

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def on_enter(self) -> None:
        """Called when the agent session starts. Initialises the scene run."""
        ud: TableReadUserData = self.session.userdata

        # Reset session state for a fresh run
        ud.session_state.status = SceneStatus.RUNNING
        ud.session_state.beat_index = 0
        ud.session_state.last_talk_turn = None
        ud.session_state.transcript = []
        ud.session_state.director_events = []
        ud.session_state.actor_latest_takes = {}
        ud.session_state.locked_script_text = None
        ud.session_state.locked_notes = None

        save_session(ud.settings, ud.scene.scene_id, ud.session_state)
        logger.info("Scene %s started – advancing initial AI beats", ud.scene.scene_id)

        await self._advance_ai_beats()

    async def on_user_turn_completed(self, event: UserTurnCompleted) -> None:
        """Handle transcribed speech from the human participant."""
        text: str = event.transcript
        if not text or not text.strip():
            return

        ud: TableReadUserData = self.session.userdata
        classification = classify_utterance(text)
        logger.debug("Utterance classified as '%s': %s", classification, text)

        if classification == "lock":
            self._record_transcript("ACTOR", text, {"intent": "lock"})
            await self._lock_scene()
            await self._send_beat_update()
            return

        if classification == "director_cmd":
            self._record_transcript("DIRECTOR", text, {"intent": "director_cmd"})
            result = apply_director_command(ud.scene, ud.session_state, text)

            # Persist the director event
            director_evt = DirectorEvent(
                cmd=text,
                target_beat_id=result.target_beat_id,
                applied=result.applied,
                meta={"actions": result.actions},
            )
            ud.session_state.director_events.append(director_evt)

            # If the command rewound the beat pointer, update state
            if result.rewind_to is not None:
                ud.session_state.beat_index = result.rewind_to
                logger.info("Rewinding to beat index %d", result.rewind_to)

            save_scene(ud.settings, ud.scene)
            save_session(ud.settings, ud.scene.scene_id, ud.session_state)
            await self._send_beat_update()

            # Re-speak from the (possibly rewound) position
            await self._advance_ai_beats()
            return

        # --- classification == "actor" ---
        self._record_transcript("ACTOR", text)

        # Record the actor's latest take for the current beat
        beats = ud.scene.beats
        idx = ud.session_state.beat_index
        if idx < len(beats) and beats[idx].speaker == "ACTOR":
            ud.session_state.actor_latest_takes[beats[idx].id] = text
            ud.session_state.beat_index += 1
            ud.session_state.last_talk_turn = "ACTOR"

        save_session(ud.settings, ud.scene.scene_id, ud.session_state)
        await self._send_beat_update()

        # Fire-and-forget director evaluation if observer is attached
        if ud.director is not None:
            asyncio.create_task(self._trigger_director_evaluation(text))

        await self._advance_ai_beats()

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    async def _advance_ai_beats(self) -> None:
        """Speak consecutive AI beats starting from the current index."""
        ud: TableReadUserData = self.session.userdata
        beats = ud.scene.beats

        while ud.session_state.beat_index < len(beats):
            beat = beats[ud.session_state.beat_index]
            if beat.speaker != "AI":
                break

            text = self._active_ai_text(beat)
            if not text:
                # Skip empty beats
                ud.session_state.beat_index += 1
                continue

            # Build SSML-style markup for Cartesia emotion/speed
            emotion = emotion_from_style(ud.session_state.style)
            pace = round(ud.session_state.style.pace, 2)
            ssml_text = f'<emotion value="{emotion}"/><speed ratio="{pace}"/>{text}'

            await self.session.say(ssml_text, allow_interruptions=False)

            # Record the spoken line
            evt = TranscriptEvent(
                speaker="AI",
                text=text,
                meta={
                    "beat_id": beat.id,
                    "character": beat.character,
                    "emotion": emotion,
                },
            )
            ud.session_state.transcript.append(evt)
            append_transcript_event(ud.settings, ud.scene.scene_id, evt)

            ud.session_state.last_talk_turn = "AI"
            ud.session_state.beat_index += 1

            save_session(ud.settings, ud.scene.scene_id, ud.session_state)
            await self._send_beat_update()

            # Honour the style pause between beats
            if ud.session_state.style.pause_ms > 0:
                await asyncio.sleep(ud.session_state.style.pause_ms / 1000.0)

        # If we have exhausted all beats, mark scene ready to lock
        if ud.session_state.beat_index >= len(beats):
            if ud.session_state.status == SceneStatus.RUNNING:
                ud.session_state.status = SceneStatus.READY_TO_LOCK
                save_session(ud.settings, ud.scene.scene_id, ud.session_state)
                await self._send_beat_update()
                logger.info("All beats complete – scene is READY_TO_LOCK")

    async def _send_beat_update(self) -> None:
        """Push current beat state to the frontend via LiveKit RPC."""
        ud: TableReadUserData = self.session.userdata
        if ud.ctx is None:
            logger.warning("No room context available; skipping beat update RPC")
            return

        beats = ud.scene.beats
        idx = ud.session_state.beat_index
        current_beat = beats[idx] if idx < len(beats) else None

        payload = {
            "scene_id": ud.scene.scene_id,
            "status": ud.session_state.status.value,
            "beat_index": idx,
            "current_beat_id": current_beat.id if current_beat else None,
            "current_speaker": current_beat.speaker if current_beat else None,
            "transcript": [
                te.model_dump(mode="json") for te in ud.session_state.transcript[-5:]
            ],
            "style": ud.session_state.style.model_dump(mode="json"),
            "actor_latest_takes": ud.session_state.actor_latest_takes,
        }

        await send_rpc_to_ui_safe(ud.ctx, "beat_update", payload)

    async def _lock_scene(self) -> None:
        """Build final locked artefacts and persist them."""
        ud: TableReadUserData = self.session.userdata
        ud.session_state.status = SceneStatus.LOCKING

        lines: list[str] = []
        for beat in ud.scene.beats:
            label = beat.character or beat.speaker
            if beat.speaker == "AI":
                text = self._active_ai_text(beat) or beat.canonical or ""
            else:
                text = ud.session_state.actor_latest_takes.get(
                    beat.id, beat.canonical or ""
                )
            lines.append(f"{label}: {text}")

        locked_script_text = "\n".join(lines)
        lock_notes = self._build_lock_notes(ud.session_state)

        save_locked_artifacts(
            ud.settings, ud.scene.scene_id, locked_script_text, lock_notes
        )

        ud.session_state.locked_script_text = locked_script_text
        ud.session_state.locked_notes = lock_notes
        ud.session_state.status = SceneStatus.LOCKED
        save_session(ud.settings, ud.scene.scene_id, ud.session_state)

        # Stream the locked script to the frontend via byte stream (large payload)
        if ud.ctx is not None:
            await stream_bytes_to_ui(
                ud.ctx,
                data={
                    "scene_id": ud.scene.scene_id,
                    "locked_script_text": locked_script_text,
                    "locked_notes": lock_notes,
                },
                topic="locked_script",
                filename="locked_script.json",
                attributes={
                    "scene_id": ud.scene.scene_id,
                    "type": "locked_script",
                },
            )

        logger.info("Scene %s locked", ud.scene.scene_id)

    async def _trigger_director_evaluation(self, actor_text: str) -> None:
        """Fire-and-forget call to the director observer, if available."""
        ud: TableReadUserData = self.session.userdata
        try:
            if ud.director is not None:
                # Find the beat the actor just delivered (one before current index)
                beat_idx = ud.session_state.beat_index - 1
                if 0 <= beat_idx < len(ud.scene.beats):
                    beat = ud.scene.beats[beat_idx]
                    evaluation = await ud.director.evaluate_performance(
                        beat, actor_text, ud.session_state.style
                    )
                    if evaluation:
                        ud.evaluations.append(evaluation)
        except Exception:
            logger.exception("Director evaluation failed")

    # ------------------------------------------------------------------
    # Pure helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _active_ai_text(beat: Beat) -> str | None:
        """Return the active variant text for a beat, falling back to canonical."""
        if beat.active_variant_id and beat.variants:
            for variant in beat.variants:
                if variant.id == beat.active_variant_id:
                    return variant.text
        return beat.canonical

    @staticmethod
    def _build_lock_notes(state: SessionState) -> list[str]:
        """Produce human-readable summary notes for the locked scene."""
        notes: list[str] = []
        total_events = len(state.transcript)
        ai_events = sum(1 for e in state.transcript if e.speaker == "AI")
        actor_events = sum(1 for e in state.transcript if e.speaker == "ACTOR")
        director_events_count = len(state.director_events)
        takes_count = len(state.actor_latest_takes)

        notes.append(f"Total transcript events: {total_events}")
        notes.append(f"AI lines spoken: {ai_events}")
        notes.append(f"Actor lines spoken: {actor_events}")
        notes.append(f"Director commands: {director_events_count}")
        notes.append(f"Actor takes recorded: {takes_count}")
        notes.append(
            f"Final style: tension={state.style.tension:.2f}, "
            f"warmth={state.style.warmth:.2f}, "
            f"pace={state.style.pace:.2f}, "
            f"pause_ms={state.style.pause_ms}"
        )
        return notes

    # ------------------------------------------------------------------
    # Transcript recording helper
    # ------------------------------------------------------------------

    def _record_transcript(
        self,
        speaker: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Append a transcript event to both in-memory state and disk."""
        ud: TableReadUserData = self.session.userdata
        evt = TranscriptEvent(speaker=speaker, text=text, meta=meta or {})
        ud.session_state.transcript.append(evt)
        append_transcript_event(ud.settings, ud.scene.scene_id, evt)
