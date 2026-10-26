"""Objects shared by the routes: settings, database engine, loaded models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine

from contractguard.config import Settings
from contractguard.pipeline import Resources


@dataclass
class AppState:
    settings: Settings
    engine: Engine
    uploads_dir: Path
    policies_dir: Path
    resources: Resources | None = None
    load_error: str | None = None


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.cg
    return state
