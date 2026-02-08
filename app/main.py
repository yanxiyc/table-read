from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import router as scenes_router
from app.runtime.engine import SceneRuntimeEngine
from app.tts import CartesiaTTSClient


def create_app() -> FastAPI:
    app = FastAPI(title="Table Read API")
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    tts_client = CartesiaTTSClient(settings)
    runtime_engine = SceneRuntimeEngine(settings=settings, tts_client=tts_client)

    app.state.settings = settings
    app.state.tts_client = tts_client
    app.state.runtime_engine = runtime_engine

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scenes_router)

    return app


app = create_app()
