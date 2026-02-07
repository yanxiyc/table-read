from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Optional
from uuid import uuid4

import websockets
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi import WebSocketDisconnect
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


def _engine_ws(websocket: WebSocket):
    return websocket.app.state.runtime_engine


def _stt_client_ws(websocket: WebSocket):
    return websocket.app.state.stt_client


def _livekit_tokens(request: Request):
    return request.app.state.livekit_tokens


def _cartesia_auth(request: Request):
    return request.app.state.cartesia_auth


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


@router.post("/{scene_id}/end")
async def end_scene(scene_id: str, request: Request):
    try:
        state = _engine(request).end_scene(scene_id, lock=True)
        return {"ok": True, "state": state}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{scene_id}/livekit-token")
async def livekit_token(scene_id: str, request: Request):
    try:
        _engine(request).load_scene(scene_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    room_name = f"table-read-{scene_id}"
    identity = f"director-{uuid4().hex[:8]}"
    try:
        token_payload = _livekit_tokens(request).create_room_token(
            room_name=room_name,
            identity=identity,
            name="director",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return token_payload


@router.get("/{scene_id}/agent-session")
async def agent_session(scene_id: str, request: Request):
    try:
        _engine(request).load_scene(scene_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    settings = _settings(request)
    if not settings.cartesia_agent_id:
        raise HTTPException(status_code=400, detail="CARTESIA_AGENT_ID is not configured.")

    try:
        access_token = _cartesia_auth(request).create_access_token(expires_in_seconds=1800)
        ws_url = _cartesia_auth(request).build_stream_url(access_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to initialize agent session: {exc}") from exc

    return {
        "agent_id": settings.cartesia_agent_id,
        "ws_url": ws_url,
        "input_format": "pcm_16000",
    }


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


@router.websocket("/{scene_id}/stream")
async def stream_scene_stt(scene_id: str, websocket: WebSocket):
    await websocket.accept()
    engine = _engine_ws(websocket)
    stt_client = _stt_client_ws(websocket)

    try:
        engine.load_scene(scene_id)
    except FileNotFoundError:
        await websocket.send_json({"type": "error", "message": f"Scene '{scene_id}' not found."})
        await websocket.close(code=4404)
        return

    try:
        cartesia_ws_url = stt_client.build_stream_url()
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": f"STT stream setup failed: {exc}"})
        await websocket.close(code=4400)
        return

    try:
        async with websockets.connect(cartesia_ws_url, ping_interval=20, ping_timeout=20) as cartesia_ws:
            await websocket.send_json({"type": "ready"})

            stop_event = asyncio.Event()

            async def client_to_cartesia() -> None:
                try:
                    while not stop_event.is_set():
                        message = await websocket.receive()
                        if message.get("type") == "websocket.disconnect":
                            break
                        data = message.get("bytes")
                        text = message.get("text")
                        if data:
                            await cartesia_ws.send(data)
                            continue
                        if text:
                            try:
                                parsed = json.loads(text)
                            except json.JSONDecodeError:
                                parsed = {"type": text}
                            if parsed.get("type") == "close":
                                break
                    stop_event.set()
                except WebSocketDisconnect:
                    stop_event.set()

            async def cartesia_to_client() -> None:
                while not stop_event.is_set():
                    try:
                        raw = await cartesia_ws.recv()
                    except Exception:
                        stop_event.set()
                        break
                    parsed = stt_client.decode_stream_message(raw)
                    if not parsed:
                        continue
                    text = stt_client.extract_transcript_text(parsed)
                    if not text:
                        continue

                    if stt_client.is_final_transcript(parsed):
                        try:
                            result = engine.submit_utterance_text(scene_id, text)
                            await websocket.send_json(
                                {
                                    "type": "final_transcript",
                                    "text": text,
                                    "kind": result.kind,
                                    "applied_actions": result.applied_actions,
                                    "state": result.state.model_dump(mode="json"),
                                }
                            )
                        except Exception as exc:
                            await websocket.send_json(
                                {"type": "error", "message": f"Command handling failed: {exc}", "text": text}
                            )
                    else:
                        await websocket.send_json({"type": "partial_transcript", "text": text})

            producer_task = asyncio.create_task(client_to_cartesia())
            consumer_task = asyncio.create_task(cartesia_to_client())
            done, pending = await asyncio.wait(
                [producer_task, consumer_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            for task in done:
                if task.exception():
                    raise task.exception()

    except Exception as exc:
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": f"Stream closed: {exc}"})
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()


@router.get("/{scene_id}/audio/{filename}")
async def get_audio(scene_id: str, filename: str, request: Request):
    safe_name = Path(filename).name
    target = files.audio_dir(_settings(request), scene_id) / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Audio not found.")
    return FileResponse(target)
