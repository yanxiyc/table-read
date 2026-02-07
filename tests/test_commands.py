from app.models import Beat, Scene, SessionState
from app.runtime.commands import apply_director_command, classify_utterance


def _scene() -> Scene:
    return Scene(
        scene_id="s1",
        title="test",
        characters={"AI": "A", "ACTOR": "B"},
        voice={"ai_voice_id": "voice-1"},
        beats=[
            Beat(id="b1", speaker="AI", canonical="Line 1"),
            Beat(id="b2", speaker="ACTOR"),
            Beat(id="b3", speaker="AI", canonical="Line 3"),
            Beat(id="b4", speaker="ACTOR"),
        ],
    )


def test_classification_works():
    assert classify_utterance("ok scene lock this version") == "lock"
    assert classify_utterance("reader one more time but slower") == "director_cmd"
    assert classify_utterance("I was in traffic") == "actor"
    assert classify_utterance("I said this line again yesterday") == "actor"
    assert classify_utterance("can you do it again but faster") == "director_cmd"


def test_director_command_replay_and_style():
    scene = _scene()
    state = SessionState(beat_index=3, last_talk_turn="AI")
    result = apply_director_command(scene, state, "reader one more time but slower")

    assert result.applied is True
    assert result.rewind_to == 2
    assert "pace:slower" in result.actions
    assert state.style.pace < 1.0


def test_explicit_variant_updates_ai_line():
    scene = _scene()
    state = SessionState(beat_index=3, last_talk_turn="ACTOR")
    result = apply_director_command(scene, state, "reader try this: New line C")

    assert result.applied is True
    assert result.rewind_to == 2
    assert scene.beats[2].active_variant_id is not None
    assert scene.beats[2].variants[-1].text == "New line C"
