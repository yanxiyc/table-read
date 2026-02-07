from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from app.models import Beat, Scene, SessionState, StyleState, Variant

LOCK_PATTERNS = (
    re.compile(r"\block this version\b", re.IGNORECASE),
    re.compile(r"\bok scene[, ]+lock this version\b", re.IGNORECASE),
)

DIRECTOR_EXPLICIT_PATTERN = re.compile(r"^\s*reader\b", re.IGNORECASE)

DIRECTOR_PREFIX_PATTERNS = (
    re.compile(r"^\s*(again|redo|one more time|do it again)\b", re.IGNORECASE),
    re.compile(r"^\s*(wait|stop)\b", re.IGNORECASE),
    re.compile(r"^\s*(try this|say|change the line|try it like|how about this line)\b", re.IGNORECASE),
    re.compile(
        r"^\s*(can you|could you)\b.*\b(again|redo|slower|faster|warmer|cooler|cold|tense)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(slower|faster|warmer|cooler|cold|tense)\b",
        re.IGNORECASE,
    ),
)

EXPLICIT_LINE_PATTERNS = (
    re.compile(r"\btry this\b\s*[-:]*\s*(?P<line>.+)$", re.IGNORECASE),
    re.compile(r"\bsay\b\s+(?P<line>.+)$", re.IGNORECASE),
    re.compile(r"\bhow about this line\b\s*[:\-]*\s*(?P<line>.+)$", re.IGNORECASE),
    re.compile(r"\bchange the line to\b\s+(?P<line>.+)$", re.IGNORECASE),
)


@dataclass
class CommandResult:
    applied: bool = False
    actions: list[str] = field(default_factory=list)
    target_beat_id: Optional[str] = None
    rewind_to: Optional[int] = None


def is_lock_phrase(text: str) -> bool:
    candidate = text.strip()
    return any(pattern.search(candidate) for pattern in LOCK_PATTERNS)


def is_director_command(
    text: str,
    state: Optional[SessionState] = None,
    current_speaker: Optional[Literal["AI", "ACTOR"]] = None,
) -> bool:
    candidate = text.strip()
    if DIRECTOR_EXPLICIT_PATTERN.search(candidate):
        return True

    if not any(pattern.search(candidate) for pattern in DIRECTOR_PREFIX_PATTERNS):
        return False

    if state is None:
        return True

    if current_speaker in {"AI", "ACTOR"}:
        return True

    if state.status.value in {"RUNNING", "READY_TO_LOCK"}:
        return True

    return False


def classify_utterance(
    text: str,
    state: Optional[SessionState] = None,
    current_speaker: Optional[Literal["AI", "ACTOR"]] = None,
) -> str:
    if is_lock_phrase(text):
        return "lock"
    if is_director_command(text, state=state, current_speaker=current_speaker):
        return "director_cmd"
    return "actor"


def apply_director_command(scene: Scene, state: SessionState, text: str) -> CommandResult:
    result = CommandResult()
    lower = text.lower()
    style_actions = _apply_style_modifiers(state.style, lower)
    result.actions.extend(style_actions)

    explicit_line = _extract_explicit_line(text)
    if explicit_line:
        target_idx = _find_target_ai_index(scene.beats, state.beat_index)
        if target_idx is not None:
            beat = scene.beats[target_idx]
            variant = Variant(
                id=f"v{len(beat.variants) + 1}",
                text=explicit_line.strip(),
                source="director_explicit",
            )
            beat.variants.append(variant)
            beat.active_variant_id = variant.id
            result.target_beat_id = beat.id
            result.rewind_to = target_idx
            result.actions.append(f"variant:{beat.id}")
            result.applied = True

    elif "change the line" in lower or "try it like" in lower:
        target_idx = _find_target_ai_index(scene.beats, state.beat_index)
        if target_idx is not None:
            beat = scene.beats[target_idx]
            prompt = _extract_change_prompt(text)
            base = beat.canonical or ""
            rewritten = _heuristic_rewrite(base, prompt)
            variant = Variant(
                id=f"v{len(beat.variants) + 1}",
                text=rewritten,
                source="director_rewrite",
            )
            beat.variants.append(variant)
            beat.active_variant_id = variant.id
            result.target_beat_id = beat.id
            result.rewind_to = target_idx
            result.actions.append(f"rewrite:{beat.id}")
            result.applied = True

    if _is_replay_intent(lower) and result.rewind_to is None:
        rewind_index = _find_rewind_index(scene, state)
        if rewind_index is not None:
            result.rewind_to = rewind_index
            result.actions.append(f"rewind:{rewind_index}")
            result.target_beat_id = scene.beats[rewind_index].id
            result.applied = True

    if style_actions:
        result.applied = True

    return result


def _apply_style_modifiers(style: StyleState, lower_text: str) -> list[str]:
    actions: list[str] = []
    if "slower" in lower_text:
        style.pace = _clamp(style.pace - 0.1, 0.8, 1.2)
        style.pause_ms = int(_clamp(style.pause_ms + 80, 100, 2000))
        actions.append("pace:slower")
    if "faster" in lower_text:
        style.pace = _clamp(style.pace + 0.1, 0.8, 1.2)
        style.pause_ms = int(_clamp(style.pause_ms - 80, 100, 2000))
        actions.append("pace:faster")
    if "warmer" in lower_text:
        style.warmth = _clamp(style.warmth + 0.2, -1.0, 1.0)
        actions.append("warmth:up")
    if "cooler" in lower_text or re.search(r"\bcold\b", lower_text):
        style.warmth = _clamp(style.warmth - 0.2, -1.0, 1.0)
        actions.append("warmth:down")
    if "tense" in lower_text or "tension" in lower_text:
        style.tension = _clamp(style.tension + 0.2, 0.0, 1.0)
        actions.append("tension:up")
    return actions


def _find_target_ai_index(beats: list[Beat], beat_index: int) -> Optional[int]:
    if 0 <= beat_index < len(beats) and beats[beat_index].speaker == "AI":
        return beat_index
    for idx in range(beat_index, len(beats)):
        if beats[idx].speaker == "AI":
            return idx
    for idx in range(beat_index - 1, -1, -1):
        if beats[idx].speaker == "AI":
            return idx
    return None


def _find_rewind_index(scene: Scene, state: SessionState) -> Optional[int]:
    beats = scene.beats
    if not beats:
        return None

    current_idx = min(state.beat_index, len(beats) - 1)

    if state.last_talk_turn == "AI":
        if current_idx >= 0 and beats[current_idx].speaker == "AI":
            return current_idx
        for idx in range(current_idx - 1, -1, -1):
            if beats[idx].speaker == "AI":
                return idx
        return 0

    if state.last_talk_turn == "ACTOR":
        if current_idx >= 0 and beats[current_idx].speaker == "ACTOR":
            return current_idx
        for idx in range(current_idx - 1, -1, -1):
            if beats[idx].speaker == "ACTOR":
                return idx
        return 0

    return max(0, current_idx - 1)


def _extract_explicit_line(text: str) -> Optional[str]:
    for pattern in EXPLICIT_LINE_PATTERNS:
        match = pattern.search(text.strip())
        if match:
            line = match.group("line").strip().strip("\"'")
            if line:
                return line
    return None


def _extract_change_prompt(text: str) -> str:
    lowered = text.lower()
    marker = "change the line"
    if marker in lowered:
        idx = lowered.index(marker) + len(marker)
        return text[idx:].strip(" :.-")

    marker = "try it like"
    if marker in lowered:
        idx = lowered.index(marker) + len(marker)
        return text[idx:].strip(" :.-")

    return ""


def _heuristic_rewrite(canonical: str, prompt: str) -> str:
    prompt = prompt.strip()
    if not prompt:
        return canonical
    if canonical:
        return f"{canonical} [{prompt}]"
    return prompt


def _is_replay_intent(lower_text: str) -> bool:
    replay_markers = ("again", "redo", "one more time", "do it again")
    return any(marker in lower_text for marker in replay_markers)


def _clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))
