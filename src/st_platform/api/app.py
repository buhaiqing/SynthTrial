"""FastAPI application factory (M11 T-M11-04)."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import reports, runs


def create_app() -> FastAPI:
    app = FastAPI(title="SynthTrial", version="0.1")
    app.include_router(runs.router, prefix="/runs", tags=["runs"])
    app.include_router(reports.router, prefix="/reports", tags=["reports"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app