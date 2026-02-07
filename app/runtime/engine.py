from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

from app.config import Settings
from app.integrations.cartesia_tts import CartesiaTTSClient
from app.models import (
    DirectorEvent,
    Scene,
    SceneStatus,
    SessionState,
    StateResponse,
    TranscriptEvent,
)
from app.runtime.commands import apply_director_command, classify_utterance
from app.storage import files


@dataclass
class UtteranceResult:
    text: str
    kind: Literal["actor", "director_cmd", "lock"]
    applied_actions: list[str]
    state: StateResponse


class SceneRuntimeEngine:
    def __init__(self, settings: Settings, tts_client: CartesiaTTSClient):
        self._settings = settings
        self._tts_client = tts_client
        self._lock = threading.RLock()
        self._state_cache: dict[str, SessionState] = {}

    def create_scene(self, scene: Scene) -> None:
        files.save_scene(self._settings, scene)
        state = SessionState(status=SceneStatus.IDLE)
        files.save_session(self._settings, scene.scene_id, state)
        self._state_cache[scene.scene_id] = state

    def load_scene(self, scene_id: str) -> Scene:
        return files.load_scene(self._settings, scene_id)

    def get_state(self, scene_id: str) -> StateResponse:
        with self._lock:
            scene = self.load_scene(scene_id)
            state = self._load_or_init_state(scene_id)
            return self._state_response(scene, state)

    def start_scene(self, scene_id: str) -> StateResponse:
        with self._lock:
            scene = self.load_scene(scene_id)
            state = self._load_or_init_state(scene_id)

            if state.status == SceneStatus.LOCKED:
                raise ValueError("Scene is locked and cannot be restarted.")

            if state.status == SceneStatus.RUNNING:
                return self._state_response(scene, state)

            state.status = SceneStatus.RUNNING
            state.beat_index = 0
            state.last_talk_turn = None
            state.style.pace = self._settings.default_pace
            state.style.pause_ms = 350
            state.style.tension = 0.5
            state.style.warmth = 0.0
            state.transcript = []
            state.director_events = []
            state.locked_notes = None
            state.locked_script_text = None
            state.actor_latest_takes = {}
            self._save_state(scene_id, state)

            self._advance_ai(scene, state)
            return self._state_response(scene, state)

    def submit_utterance_text(self, scene_id: str, text: str) -> UtteranceResult:
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("Utterance text is empty.")

        with self._lock:
            scene = self.load_scene(scene_id)
            state = self._load_or_init_state(scene_id)
            if state.status not in {SceneStatus.RUNNING, SceneStatus.READY_TO_LOCK}:
                raise RuntimeError(f"Scene is not accepting utterances in status={state.status}.")

            kind = classify_utterance(normalized_text)
            actions: list[str] = []

            if kind == "lock":
                self._append_transcript(
                    scene_id,
                    state,
                    TranscriptEvent(
                        speaker="DIRECTOR",
                        text=normalized_text,
                        meta={"classification": "lock_phrase"},
                    ),
                )
                self._lock_scene(scene_id, scene, state)
                return UtteranceResult(
                    text=normalized_text,
                    kind="lock",
                    applied_actions=["lock_scene"],
                    state=self._state_response(scene, state),
                )

            if kind == "director_cmd":
                result = apply_director_command(scene, state, normalized_text)
                state.director_events.append(
                    DirectorEvent(
                        cmd=normalized_text,
                        target_beat_id=result.target_beat_id,
                        applied=result.applied,
                        meta={"actions": result.actions},
                    )
                )
                self._append_transcript(
                    scene_id,
                    state,
                    TranscriptEvent(
                        speaker="DIRECTOR",
                        text=normalized_text,
                        meta={"classification": "director_cmd", "actions": result.actions},
                    ),
                )
                if result.rewind_to is not None:
                    state.beat_index = max(0, min(result.rewind_to, len(scene.beats)))
                    if state.status == SceneStatus.READY_TO_LOCK:
                        state.status = SceneStatus.RUNNING
                actions = result.actions
                files.save_scene(self._settings, scene)
                self._save_state(scene_id, state)
                self._advance_ai(scene, state)
                return UtteranceResult(
                    text=normalized_text,
                    kind="director_cmd",
                    applied_actions=actions,
                    state=self._state_response(scene, state),
                )

            # Actor line
            if state.beat_index < len(scene.beats) and scene.beats[state.beat_index].speaker == "ACTOR":
                beat = scene.beats[state.beat_index]
                state.actor_latest_takes[beat.id] = normalized_text
                state.last_talk_turn = "ACTOR"
                self._append_transcript(
                    scene_id,
                    state,
                    TranscriptEvent(
                        speaker="ACTOR",
                        text=normalized_text,
                        meta={
                            "beat_id": beat.id,
                            "character": beat.character or scene.characters.get("ACTOR", "ACTOR"),
                        },
                    ),
                )
                state.beat_index += 1
                if state.beat_index >= len(scene.beats):
                    state.status = SceneStatus.READY_TO_LOCK
                else:
                    state.status = SceneStatus.RUNNING
                self._save_state(scene_id, state)
                self._advance_ai(scene, state)
                return UtteranceResult(
                    text=normalized_text,
                    kind="actor",
                    applied_actions=[],
                    state=self._state_response(scene, state),
                )

            self._append_transcript(
                scene_id,
                state,
                TranscriptEvent(
                    speaker="UNKNOWN",
                    text=normalized_text,
                    meta={"reason": "out_of_turn_actor_input"},
                ),
            )
            self._save_state(scene_id, state)
            return UtteranceResult(
                text=normalized_text,
                kind="actor",
                applied_actions=["ignored_out_of_turn"],
                state=self._state_response(scene, state),
            )

    def _advance_ai(self, scene: Scene, state: SessionState) -> None:
        while state.status == SceneStatus.RUNNING and state.beat_index < len(scene.beats):
            beat = scene.beats[state.beat_index]
            if beat.speaker != "AI":
                break
            text = self._active_ai_text(beat)
            transcript_event = TranscriptEvent(
                speaker="AI",
                text=text,
                meta={
                    "beat_id": beat.id,
                    "character": beat.character or scene.characters.get("AI", "AI"),
                    "style": state.style.model_dump(mode="json"),
                },
            )
            try:
                audio_url = self._tts_client.speak(
                    scene.scene_id,
                    transcript_event.event_id,
                    text,
                    scene.voice.get("ai_voice_id", ""),
                    state.style,
                )
                if audio_url:
                    transcript_event.meta["audio_url"] = audio_url
            except Exception as exc:  # pragma: no cover - network failures are runtime concerns
                transcript_event.meta["tts_error"] = str(exc)

            self._append_transcript(scene.scene_id, state, transcript_event)
            state.last_talk_turn = "AI"
            state.beat_index += 1
            self._save_state(scene.scene_id, state)

        if state.beat_index >= len(scene.beats) and state.status == SceneStatus.RUNNING:
            state.status = SceneStatus.READY_TO_LOCK
            self._save_state(scene.scene_id, state)

    def _lock_scene(self, scene_id: str, scene: Scene, state: SessionState) -> None:
        state.status = SceneStatus.LOCKING
        self._save_state(scene_id, state)

        lines: list[str] = []
        for beat in scene.beats:
            label = beat.character or ("AI" if beat.speaker == "AI" else "ACTOR")
            if beat.speaker == "AI":
                lines.append(f"{label}: {self._active_ai_text(beat)}")
                continue
            actor_text = state.actor_latest_takes.get(beat.id)
            final_text = actor_text if actor_text is not None else (beat.canonical or "")
            lines.append(f"{label}: {final_text}" if final_text else f"{label}:")

        locked_script = "\n".join(lines)
        notes = self._build_lock_notes(state)
        state.locked_script_text = locked_script
        state.locked_notes = notes
        state.status = SceneStatus.LOCKED
        self._append_transcript(
            scene_id,
            state,
            TranscriptEvent(
                speaker="SYSTEM",
                text="Scene locked.",
                meta={"status": "LOCKED"},
            ),
        )
        files.save_scene(self._settings, scene)
        files.save_locked_artifacts(self._settings, scene_id, locked_script, notes)
        self._save_state(scene_id, state)

    def _active_ai_text(self, beat) -> str:
        if beat.active_variant_id:
            for variant in beat.variants:
                if variant.id == beat.active_variant_id:
                    return variant.text
        return beat.canonical or ""

    def _build_lock_notes(self, state: SessionState) -> list[str]:
        ai_count = sum(1 for event in state.transcript if event.speaker == "AI")
        actor_count = sum(1 for event in state.transcript if event.speaker == "ACTOR")
        command_count = sum(1 for event in state.director_events if event.applied)
        return [
            (
                f"Final style: pace={state.style.pace:.2f}, tension={state.style.tension:.2f}, "
                f"warmth={state.style.warmth:.2f}, pause_ms={state.style.pause_ms}"
            ),
            f"Applied director commands: {command_count}",
            f"Transcript summary: ai_lines={ai_count}, actor_lines={actor_count}",
        ]

    def _append_transcript(self, scene_id: str, state: SessionState, event: TranscriptEvent) -> None:
        state.transcript.append(event)
        files.append_transcript_event(self._settings, scene_id, event)

    def _load_or_init_state(self, scene_id: str) -> SessionState:
        state = self._state_cache.get(scene_id)
        if state:
            return state
        loaded = files.load_session(self._settings, scene_id)
        if loaded:
            self._state_cache[scene_id] = loaded
            return loaded
        state = SessionState()
        self._state_cache[scene_id] = state
        return state

    def _save_state(self, scene_id: str, state: SessionState) -> None:
        files.save_session(self._settings, scene_id, state)
        self._state_cache[scene_id] = state

    def _state_response(self, scene: Scene, state: SessionState) -> StateResponse:
        current_beat_id = None
        current_speaker = None
        if 0 <= state.beat_index < len(scene.beats):
            current_beat = scene.beats[state.beat_index]
            current_beat_id = current_beat.id
            current_speaker = current_beat.speaker
        return StateResponse(
            scene_id=scene.scene_id,
            status=state.status,
            beat_index=state.beat_index,
            current_beat_id=current_beat_id,
            current_speaker=current_speaker,
            transcript=state.transcript,
            director_events=state.director_events,
            locked_script_text=state.locked_script_text,
            locked_notes=state.locked_notes,
            style=state.style,
        )
