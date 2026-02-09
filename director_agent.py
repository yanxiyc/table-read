"""LiveKit director agent entry point (standalone participant)."""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli, inference
from livekit.agents.voice import AgentSession
from livekit.plugins import silero

from app.agents.director_agent import DirectorAgent, DirectorUserData
from app.config import get_settings
from app.storage import load_scene_smart

load_dotenv()
logger = logging.getLogger("table-read-director")


def prewarm(proc):
    """Pre-load the Silero VAD model to avoid cold-start latency."""
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    """Main entry point for the director agent session."""
    await ctx.connect()

    room_name = ctx.room.name
    if room_name.startswith("table-read-"):
        scene_id = room_name[len("table-read-") :]
    else:
        scene_id = room_name

    settings = get_settings()
    scene = await load_scene_smart(settings, scene_id)

    userdata = DirectorUserData(scene=scene, settings=settings, ctx=ctx)

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()

    session = AgentSession[DirectorUserData](
        userdata=userdata,
        vad=vad,
        stt=inference.STT(model="cartesia/ink-whisper"),
        llm=inference.LLM(model="anthropic/claude-sonnet-4-5-20250929"),
        tts=inference.TTS(model="cartesia/sonic-3"),
    )

    # Register RPC handler so the character agent's beat_update
    # messages keep the director's beat pointer in sync (handles rewinds).
    @ctx.room.local_participant.register_rpc_method("beat_update")
    async def _on_beat_update(data):
        import json as _json

        try:
            payload = _json.loads(data.payload)
            new_idx = payload.get("beat_index", 0)
            userdata.last_known_beat_index = new_idx
            if payload.get("current_speaker") == "ACTOR":
                userdata.last_actor_beat_id = payload.get("current_beat_id")
        except Exception:
            pass

    logger.info(
        "Starting director agent for scene %s (room: %s)",
        scene_id,
        room_name,
    )

    await session.start(
        agent=DirectorAgent(),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            agent_name="table-read-director",
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
