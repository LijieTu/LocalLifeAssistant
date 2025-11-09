#!/usr/bin/env python3
"""
Event provider base definitions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class EventProvider(ABC):
    """Abstract base class for event providers."""

    name: str

    @abstractmethod
    def supports_city(self, city: str) -> bool:
        """Return True when provider can serve the given city."""

    @abstractmethod
    def fetch_events(
        self,
        city: str,
        *,
        max_pages: int = 3,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch events for the given city."""


