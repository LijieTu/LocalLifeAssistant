#!/usr/bin/env python3
"""
System and diagnostics endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ...core.container import ServiceContainer, get_service_container

router = APIRouter()

logger = logging.getLogger(__name__)


def get_container() -> ServiceContainer:
    return get_service_container()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "2.1.0",
        "features": ["smart_caching", "real_time_events", "city_based_cache"],
    }


@router.get("/stats")
async def get_stats(container: ServiceContainer = Depends(get_container)):
    """Get system statistics including cache info."""
    cache_manager = container.cache_manager
    try:
        cache_stats = cache_manager.get_cache_stats()
        return {
            "status": "active",
            "cache_stats": cache_stats,
            "features": ["smart_caching", "real_time_events", "city_based_cache", "llm_city_extraction"],
        }
    except Exception as exc:
        logger.error("Error getting stats: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.post("/api/cache/cleanup")
async def cleanup_cache(container: ServiceContainer = Depends(get_container)):
    """Manually clean up expired cache files."""
    cache_manager = container.cache_manager
    try:
        cache_manager.cleanup_old_cache()
        stats = cache_manager.get_cache_stats()
        return {
            "success": True,
            "message": "Cache cleanup completed",
            "stats": stats,
        }
    except Exception as exc:
        logger.error("Error cleaning up cache: %s", exc)
        return {
            "success": False,
            "error": str(exc),
        }


@router.get("/api/cache/stats")
async def get_cache_stats(container: ServiceContainer = Depends(get_container)):
    """Get detailed cache statistics."""
    cache_manager = container.cache_manager
    try:
        stats = cache_manager.get_cache_stats()
        return {
            "success": True,
            "stats": stats,
        }
    except Exception as exc:
        logger.error("Error getting cache stats: %s", exc)
        return {
            "success": False,
            "error": str(exc),
        }


