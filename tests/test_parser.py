import pytest

from app.parser import ScriptParseError, parse_script


def test_parse_script_success():
    beats = parse_script(
        """MOTHER: You're late.
YOU:
MOTHER: Don't do this here.
YOU:
""",
        ai_character_name="MOTHER",
    )
    assert len(beats) == 4
    assert beats[0].speaker == "AI"
    assert beats[0].character == "MOTHER"
    assert beats[0].canonical == "You're late."
    assert beats[1].speaker == "ACTOR"
    assert beats[1].character == "YOU"


def test_parse_script_invalid_line():
    with pytest.raises(ScriptParseError):
        parse_script("NARRATOR hello", ai_character_name="MOTHER")


def test_parse_script_requires_ai_character_lines():
    with pytest.raises(ScriptParseError):
        parse_script("YOU: hello", ai_character_name="MOTHER")
