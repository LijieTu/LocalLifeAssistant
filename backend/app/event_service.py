#!/usr/bin/env python3
"""Compatibility wrapper for legacy event crawler imports."""

from __future__ import annotations

from typing import Dict, Any, Iterable, List, Optional, Sequence

from .services.events import EventAggregator, create_default_aggregator
from .services.events.provider_base import EventProvider


class EventCrawler:
    """Historical facade kept for backwards compatibility."""

    def __init__(
        self,
        *,
        providers: Optional[Iterable[EventProvider]] = None,
    ) -> None:
        if providers is None:
            self._aggregator = create_default_aggregator()
        else:
            self._aggregator = EventAggregator(providers)

    def fetch_events_by_city(
        self,
        city_name: str,
        max_pages: int = 3,
        *,
        sources: Optional[Sequence[str]] = None,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self._aggregator.fetch_by_city(
            city_name,
            provider_names=sources,
            max_pages=max_pages,
            max_results=max_results,
        )

    def fetch_events_multiple_cities(
        self,
        cities: Sequence[str],
        *,
        max_pages_per_city: int = 2,
        sources: Optional[Sequence[str]] = None,
        max_results: Optional[int] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            city: self.fetch_events_by_city(
                city,
                max_pages=max_pages_per_city,
                sources=sources,
                max_results=max_results,
            )
            for city in cities
        }


# Convenience helper retained for existing imports expecting module-level function
_event_crawler = EventCrawler()


def fetch_events_by_city(city_name: str, max_pages: int = 3) -> List[Dict[str, Any]]:
    return _event_crawler.fetch_events_by_city(city_name, max_pages=max_pages)