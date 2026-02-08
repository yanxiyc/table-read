from __future__ import annotations

from app.models import Beat


class ScriptParseError(ValueError):
    pass


def parse_script(script_text: str, ai_character_name: str) -> list[Beat]:
    ai_name = ai_character_name.strip()
    if not ai_name:
        raise ScriptParseError("AI character name is required.")

    beats: list[Beat] = []
    beat_count = 0
    ai_seen = False

    for line_no, raw_line in enumerate(script_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if ":" not in line:
            raise ScriptParseError(
                f"Line {line_no}: invalid format '{line}'. Use 'CHARACTER: <line>'."
            )

        raw_character, raw_text = line.split(":", 1)
        character = raw_character.strip()
        canonical = raw_text.strip()

        if not character:
            raise ScriptParseError(f"Line {line_no}: character name is empty.")

        is_ai = character.casefold() == ai_name.casefold()
        if is_ai and not canonical:
            raise ScriptParseError(
                f"Line {line_no}: AI beat for '{character}' must include text."
            )

        beat_count += 1
        beats.append(
            Beat(
                id=f"b{beat_count}",
                speaker="AI" if is_ai else "ACTOR",
                character=character,
                canonical=canonical or None,
            )
        )
        ai_seen = ai_seen or is_ai

    if not beats:
        raise ScriptParseError("Script is empty.")
    if not ai_seen:
        raise ScriptParseError(
            f"No lines found for AI character '{ai_name}'. Use that exact character name in script."
        )

    return beats
