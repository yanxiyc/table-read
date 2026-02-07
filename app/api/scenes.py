from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.models import CreateSceneRequest, CreateSceneResponse, Scene
from app.parser.script_parser import ScriptParseError, parse_script
from app.storage import files

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


def _engine(request: Request):
    return request.app.state.runtime_engine


def _settings(request: Request):
    return request.app.state.settings


def _stt_client(request: Request):
    return request.app.state.stt_client


@router.post("", response_model=CreateSceneResponse)
async def create_scene(payload: CreateSceneRequest, request: Request) -> CreateSceneResponse:
    try:
        beats = parse_script(payload.script_text, payload.ai_character_name)
    except ScriptParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    actor_names = sorted({beat.character for beat in beats if beat.speaker == "ACTOR" and beat.character})
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


@router.post("/{scene_id}/utterance")
async def submit_utterance(
    scene_id: str,
    request: Request,
    audio: Optional[UploadFile] = File(default=None),
    text_override: Optional[str] = Form(default=None),
    client_ts: Optional[str] = Form(default=None),
):
    try:
        _engine(request).load_scene(scene_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    text = (text_override or "").strip()
    if not text:
        if audio is None:
            raise HTTPException(status_code=400, detail="Either audio file or text_override is required.")
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Uploaded audio is empty.")
        try:
            text = _stt_client(request).transcribe_utterance(
                audio_bytes=audio_bytes,
                mime_type=audio.content_type or "audio/wav",
                filename=audio.filename or "utterance.wav",
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"STT failed: {exc}") from exc

    if not text:
        raise HTTPException(status_code=422, detail="No speech detected in utterance.")

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
        "client_ts": client_ts,
        "state": result.state,
    }


@router.get("/{scene_id}/audio/{filename}")
async def get_audio(scene_id: str, filename: str, request: Request):
    safe_name = Path(filename).name
    target = files.audio_dir(_settings(request), scene_id) / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Audio not found.")
    return FileResponse(target)
