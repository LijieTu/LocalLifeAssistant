#!/usr/bin/env python3
"""
Event provider aggregation utilities.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .provider_base import EventProvider
from .eventbrite import EventbriteProvider

logger = logging.getLogger(__name__)


class EventAggregator:
    """Aggregates events from multiple providers."""

    def __init__(self, providers: Optional[Iterable[EventProvider]] = None):
        self._providers: List[EventProvider] = list(providers or [])

    @property
    def providers(self) -> Sequence[EventProvider]:
        return tuple(self._providers)

    def register(self, provider: EventProvider) -> None:
        if provider not in self._providers:
            self._providers.append(provider)

    def fetch_by_city(
        self,
        city: str,
        *,
        provider_names: Optional[Sequence[str]] = None,
        max_pages: int = 3,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        selected = self._select_providers(provider_names)
        events: List[Dict[str, Any]] = []

        for provider in selected:
            if not provider.supports_city(city):
                logger.debug("%s does not support city '%s'", provider.name, city)
                continue
            provider_events = provider.fetch_events(
                city,
                max_pages=max_pages,
                max_results=max_results,
            )
            events.extend(provider_events)

        return events

    def _select_providers(self, provider_names: Optional[Sequence[str]]) -> List[EventProvider]:
        if not provider_names:
            return list(self._providers)

        names = {name.lower() for name in provider_names}
        return [provider for provider in self._providers if provider.name.lower() in names]


def create_default_aggregator() -> EventAggregator:
    """Construct an aggregator with default providers."""
    aggregator = EventAggregator()
    aggregator.register(EventbriteProvider())
    return aggregator


