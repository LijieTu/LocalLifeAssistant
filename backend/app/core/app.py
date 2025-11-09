#!/usr/bin/env python3
"""
FastAPI application factory.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .env import load_environment
from .logging import configure_logging
from .settings import get_settings
from ..api import api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    load_environment()
    configure_logging(logging.INFO)

    settings = get_settings()
    app = FastAPI(
        title="Smart Cached RAG Local Life Assistant",
        version="2.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
        response.headers.setdefault("Cross-Origin-Embedder-Policy", "credentialless")
        return response

    app.include_router(api_router)

    return app


