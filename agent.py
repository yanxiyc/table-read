"""LiveKit agent entry point for the Table Read application.

Run with:
    python agent.py dev
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli, inference
from livekit.agents.voice import AgentSession
from livekit.plugins import anthropic, silero

from app.agents.character_agent import ScriptedCharacterAgent
from app.agents.director_observer import DirectorObserver
from app.agents.state import TableReadUserData
from app.config import get_settings
from app.models import SessionState
from app.storage import load_scene

load_dotenv()
logger = logging.getLogger("table-read-agent")


def prewarm(proc):
    """Pre-load the Silero VAD model to avoid cold-start latency."""
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    """Main entry point for a LiveKit agent session.

    The room name is expected to be ``table-read-{scene_id}``.
    The agent loads the scene from disk, sets up TTS/STT/VAD,
    creates the DirectorObserver, and starts the ScriptedCharacterAgent.
    """
    await ctx.connect()

    # Extract scene_id from room name (format: "table-read-{scene_id}")
    room_name = ctx.room.name
    if room_name.startswith("table-read-"):
        scene_id = room_name[len("table-read-") :]
    else:
        scene_id = room_name

    settings = get_settings()

    # Load the scene from disk (must have been created via the FastAPI endpoint)
    scene = load_scene(settings, scene_id)
    ai_voice_id = scene.voice.get("ai_voice_id", "")

    # Build shared state
    userdata = TableReadUserData(
        scene=scene,
        session_state=SessionState(),
        settings=settings,
        ctx=ctx,
        ai_voice_id=ai_voice_id,
    )

    # Configure session components using inference.* API
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()

    tts_kwargs: dict = {"model": "cartesia/sonic-2"}
    if ai_voice_id:
        tts_kwargs["voice"] = ai_voice_id

    session = AgentSession[TableReadUserData](
        userdata=userdata,
        vad=vad,
        stt=inference.STT(model="cartesia/ink-whisper"),
        tts=inference.TTS(**tts_kwargs),
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
    )

    # Create the director observer (uses Anthropic Claude for evaluation)
    director_llm = anthropic.LLM(model="claude-sonnet-4-5-20250929")
    director = DirectorObserver(session=session, llm=director_llm)
    userdata.director = director

    logger.info(
        "Starting table-read agent for scene %s (room: %s)",
        scene_id,
        room_name,
    )

    # Start the session with the scripted character agent
    await session.start(
        agent=ScriptedCharacterAgent(),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
