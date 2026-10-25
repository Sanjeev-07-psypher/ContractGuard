"""FastAPI app (HLD 10). Run with ``uvicorn backend.main:app``.

Models load once at startup (lifespan). If they cannot be loaded (e.g. the classifier has not been
trained), the API still starts: ``/health`` says so and uploads return 503 with the reason.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import contracts, policies
from backend.db import make_engine
from backend.errors import install_handlers
from backend.state import AppState, get_state
from contractguard import __version__
from contractguard.config import Settings, get_settings
from contractguard.ingestion.ocr import tesseract_available
from contractguard.pipeline import Resources
from contractguard.policy.schema import policies_dir

log = logging.getLogger(__name__)
API_PREFIX = "/api/v1"


def _default_loader(settings: Settings) -> Resources:
    return Resources.load(settings, cache_path=settings.resolve_path(settings.paths.sqlite_path))


def create_app(
    settings: Settings | None = None,
    load_resources: Callable[[Settings], Resources] = _default_loader,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(
            settings=settings,
            engine=make_engine(settings.resolve_path(settings.paths.sqlite_path)),
            uploads_dir=settings.resolve_path(settings.paths.uploads_dir),
            policies_dir=policies_dir(settings),
        )
        state.uploads_dir.mkdir(parents=True, exist_ok=True)
        try:
            state.resources = load_resources(settings)
        except Exception as exc:  # start anyway; /health and uploads explain the problem
            state.load_error = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
            log.error("Models not loaded: %s", state.load_error)
        app.state.cg = state
        yield
        state.engine.dispose()

    app = FastAPI(title="ContractGuard API", version=__version__, lifespan=lifespan)
    origin = urlparse(settings.frontend.origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"{origin.scheme}://{origin.netloc}"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_handlers(app)

    api = APIRouter(prefix=API_PREFIX)

    @api.get("/health")
    def health(state: AppState = Depends(get_state)) -> dict[str, Any]:
        r = state.resources
        return {
            "status": "ok" if r is not None else "degraded",
            "models_loaded": r is not None,
            "embeddings_loaded": r is not None and r.embedder is not None,
            "tesseract_available": tesseract_available(state.settings.ocr.tesseract_cmd),
            "llm_provider": (r.provider.name if r and r.provider else "none"),
            "error": state.load_error,
            "version": __version__,
            "disclaimer": state.settings.disclaimer,
        }

    api.include_router(contracts.router)
    api.include_router(policies.router)
    app.include_router(api)
    return app


app = create_app()
