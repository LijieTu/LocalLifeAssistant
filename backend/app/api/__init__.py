#!/usr/bin/env python3
"""
API router aggregation.
"""

from __future__ import annotations

from fastapi import APIRouter

from .routers import chat, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(chat.router)


