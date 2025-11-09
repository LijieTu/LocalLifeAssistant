#!/usr/bin/env python3
"""
Backward-compatible cache manager that delegates to the new cache service.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .services.cache import CacheStore, create_cache_store

logger = logging.getLogger(__name__)


class CacheManager:
    """Thin wrapper maintained for existing imports."""

    def __init__(self, ttl_hours: int = 6, cache_dir: str = "./cache"):
        self.store: CacheStore = create_cache_store(ttl_hours, cache_dir)
        logger.info("Cache manager initialized (ttl=%sh, dir=%s)", ttl_hours, cache_dir)

    def get_cached_events(self, city: str, event_crawler=None) -> Optional[List[Dict[str, Any]]]:
        entry = self.store.load(city)
        if entry and entry.events:
            return entry.events

        if event_crawler:
            try:
                events = event_crawler.fetch_events_by_city(city)
                if events:
                    self.store.save(city, events)
                return events or None
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to fetch fresh events for %s: %s", city, exc)
        return None

    def cache_events(self, city: str, events: List[Dict[str, Any]]) -> bool:
        try:
            self.store.save(city, events)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error caching events for %s: %s", city, exc)
            return False

    def get_cache_age(self, city: str) -> Optional[float]:
        entry = self.store.load(city)
        if not entry:
            return None
        age = (datetime.now() - entry.cached_at).total_seconds() / 3600
        return max(age, 0.0)

    def cleanup_old_cache(self) -> None:
        self.store.cleanup()

    def get_cache_stats(self) -> Dict[str, Any]:
        return self.store.stats()

