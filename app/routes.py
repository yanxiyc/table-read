from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models import CreateSceneRequest, CreateSceneResponse, Scene
from app.parser import ScriptParseError, parse_script

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


def _engine(request: Request):
    return request.app.state.runtime_engine


@router.post("", response_model=CreateSceneResponse)
async def create_scene(
    payload: CreateSceneRequest, request: Request
) -> CreateSceneResponse:
    try:
        beats = parse_script(payload.script_text, payload.ai_character_name)
    except ScriptParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    actor_names = sorted(
        {beat.character for beat in beats if beat.speaker == "ACTOR" and beat.character}
    )
    actor_label = ", ".join(actor_names) if actor_names else "ACTOR"

    scene_id = str(uuid4())
    scene = Scene(
        scene_id=scene_id,
        title=payload.title,
        characters={"AI": payload.ai_character_name, "ACTOR": actor_label},
        voice={"ai_voice_id": payload.ai_voice_id},
        beats=beats,
    )
    _engine(request).create_scene(scene)
    return CreateSceneResponse(scene_id=scene_id)


@router.get("/{scene_id}")
async def get_scene(scene_id: str, request: Request):
    try:
        return _engine(request).load_scene(scene_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{scene_id}/start")
async def start_scene(scene_id: str, request: Request):
    try:
        state = _engine(request).start_scene(scene_id)
        return {"ok": True, "state": state}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{scene_id}/state")
async def get_scene_state(scene_id: str, request: Request):
    try:
        return _engine(request).get_state(scene_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class UtteranceRequest(BaseModel):
    text: str


@router.post("/{scene_id}/utterance")
async def submit_utterance(
    scene_id: str,
    payload: UtteranceRequest,
    request: Request,
):
    """Submit a text utterance for processing by the runtime engine.

    In the LiveKit flow, voice input goes through the agent directly.
    This endpoint is retained for testing and non-voice integrations.
    """
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Utterance text is empty.")

    try:
        _engine(request).load_scene(scene_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        result = _engine(request).submit_utterance_text(scene_id, text)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "text": result.text,
        "kind": result.kind,
        "applied_actions": result.applied_actions,
        "state": result.state,
    }
