from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.scenes import router as scenes_router
from app.config import get_settings
from app.integrations.cartesia_auth import CartesiaAgentAuthClient
from app.integrations.livekit_tokens import LiveKitTokenIssuer
from app.integrations.cartesia_stt import CartesiaSTTClient
from app.integrations.cartesia_tts import CartesiaTTSClient
from app.runtime.engine import SceneRuntimeEngine


BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(title="Table Read MVP")
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    tts_client = CartesiaTTSClient(settings)
    stt_client = CartesiaSTTClient(settings)
    cartesia_auth = CartesiaAgentAuthClient(settings)
    livekit_tokens = LiveKitTokenIssuer(settings)
    runtime_engine = SceneRuntimeEngine(settings=settings, tts_client=tts_client)

    app.state.settings = settings
    app.state.tts_client = tts_client
    app.state.stt_client = stt_client
    app.state.cartesia_auth = cartesia_auth
    app.state.livekit_tokens = livekit_tokens
    app.state.runtime_engine = runtime_engine

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(scenes_router)

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/create")

    @app.get("/create")
    async def create_page(request: Request):
        return templates.TemplateResponse("create.html", {"request": request})

    @app.get("/scene/{scene_id}")
    async def scene_page(scene_id: str, request: Request):
        try:
            runtime_engine.load_scene(scene_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(
            "scene.html",
            {
                "request": request,
                "scene_id": scene_id,
            },
        )

    return app


app = create_app()
