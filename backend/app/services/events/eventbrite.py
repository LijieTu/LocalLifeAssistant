#!/usr/bin/env python3
"""
Eventbrite event provider.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from .provider_base import EventProvider

logger = logging.getLogger(__name__)


class EventbriteProvider(EventProvider):
    """Provider implementation backed by the official Eventbrite API with a destination-search fallback."""

    name = "eventbrite"

    _BASE_URL = "https://www.eventbriteapi.com/v3/events/search/"
    _DESTINATION_URL = "https://www.eventbrite.com/api/v3/destination/search/"
    _DESTINATION_STABLE_ID = "3eff2ab4-0f8b-48c5-bae5-fa33a68f2342"
    _EVENTBRITE_ROOT = "https://www.eventbrite.com/"

    _CITY_TO_PLACE_ID: Dict[str, str] = {
        "san_francisco": "85922583",
        "new_york": "85977539",
        "los_angeles": "85923517",
        "miami": "85933669",
        "chicago": "85940195",
        "seattle": "101730401",
        "boston": "85950361",
    }

    _ALIAS_TO_CITY: Dict[str, str] = {
        "sf": "san_francisco",
        "san francisco": "san_francisco",
        "san-francisco": "san_francisco",
        "nyc": "new_york",
        "new york": "new_york",
        "new york city": "new_york",
        "los angeles": "los_angeles",
        "la": "los_angeles",
        "l.a.": "los_angeles",
        "miami": "miami",
        "chicago": "chicago",
        "seattle": "seattle",
        "boston": "boston",
    }

    def __init__(self) -> None:
        token = os.getenv("EVENTBRITE_API_TOKEN")
        if not token:
            logger.warning("EVENTBRITE_API_TOKEN not set. Eventbrite provider disabled.")
        self._token = token
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}" if self._token else "",
            "Accept": "application/json",
            "User-Agent": "locomoco-app/1.0",
        })
        self._destination_session: Optional[requests.Session] = None

    def supports_city(self, city: str) -> bool:
        if self._token:
            return True
        return self._resolve_city_key(city) in self._CITY_TO_PLACE_ID

    def fetch_events(
        self,
        city: str,
        *,
        max_pages: int = 3,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        city_key = self._resolve_city_key(city)

        if not self._token:
            logger.info(
                "EVENTBRITE_API_TOKEN missing. Using destination search for '%s'",
                city,
            )
            return self._fetch_via_destination(city_key, max_pages=max_pages, max_results=max_results)

        events: List[Dict[str, Any]] = []
        page = 1

        try:
            while page <= max_pages:
                params = {
                    "location.address": city,
                    "location.within": "25mi",
                    "expand": "venue,organizer,category",
                    "sort_by": "date",
                    "page": page,
                    "token": self._token,
                }

                response = self._session.get(self._BASE_URL, params=params, timeout=30)
                if response.status_code in (401, 403):
                    logger.error("Eventbrite API token rejected or unauthorized. Refresh EVENTBRITE_API_TOKEN.")
                    break
                if response.status_code == 404 and page == 1:
                    logger.warning(
                        "Eventbrite search returned 404 for %s. Falling back to default city radius.",
                        city,
                    )
                    params.pop("location.within", None)
                    params.pop("expand", None)
                    response = self._session.get(self._BASE_URL, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()
                page_events = data.get("events", [])
                if not page_events:
                    break

                normalized = [self._normalize_event(event) for event in page_events]
                events.extend(normalized)

                if max_results is not None and len(events) >= max_results:
                    return events[:max_results]

                pagination = data.get("pagination", {})
                if not pagination.get("has_more_items"):
                    break
                page += 1

        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {401, 403, 404}:
                logger.warning(
                    "Eventbrite API returned %s for '%s'. Falling back to destination search.",
                    exc.response.status_code,
                    city,
                )
                return self._fetch_via_destination(city_key, max_pages=max_pages, max_results=max_results)
            raise
        except requests.RequestException as exc:
            logger.error("Eventbrite request failed for city '%s': %s", city, exc)
            return self._fetch_via_destination(city_key, max_pages=max_pages, max_results=max_results)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected Eventbrite error for city '%s': %s", city, exc)
            return self._fetch_via_destination(city_key, max_pages=max_pages, max_results=max_results)

        if not events:
            fallback_events = self._fetch_via_destination(city_key, max_pages=max_pages, max_results=max_results)
            if fallback_events:
                return fallback_events

        return events

    def _normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        venue = event.get("venue") or {}
        organizer = event.get("organizer") or {}
        category = event.get("category") or {}

        def parse_datetime(value: Optional[str]) -> str:
            if not value:
                return ""
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
            except ValueError:
                return value

        ticket_min, ticket_max, is_free = self._extract_price_info(event)

        return {
            "event_id": str(event.get("id", "")),
            "title": event.get("name", {}).get("text", ""),
            "description": event.get("description", {}).get("text", ""),
            "start_datetime": parse_datetime((event.get("start") or {}).get("utc")),
            "end_datetime": parse_datetime((event.get("end") or {}).get("utc")),
            "timezone": (event.get("start") or {}).get("timezone", "UTC"),
            "venue_name": venue.get("name", ""),
            "venue_city": venue.get("address", {}).get("city", ""),
            "venue_country": venue.get("address", {}).get("country", ""),
            "latitude": venue.get("address", {}).get("latitude"),
            "longitude": venue.get("address", {}).get("longitude"),
            "organizer_name": organizer.get("name", ""),
            "organizer_id": str(organizer.get("id", "")),
            "ticket_min_price": ticket_min,
            "ticket_max_price": ticket_max,
            "is_free": is_free,
            "categories": [category.get("name")] if category else [],
            "image_url": self._resolve_image_url(event),
            "event_url": event.get("url", ""),
            "attendee_count": event.get("capacity", 0),
            "source": self.name,
        }

    def _extract_price_info(self, event: Dict[str, Any]) -> tuple[str, str, bool]:
        is_free = bool(event.get("is_free", False))
        min_price = "Free" if is_free else "0"
        max_price = "Free" if is_free else "0"

        ticket_classes = event.get("ticket_classes") or []
        amounts: List[float] = []
        for ticket in ticket_classes:
            cost = ticket.get("cost") or {}
            value = cost.get("major_value")
            if value is not None:
                try:
                    amounts.append(float(value))
                except ValueError:
                    continue

        if amounts:
            min_price = self._format_price(min(amounts))
            max_price = self._format_price(max(amounts))
            is_free = min(amounts) == 0

        return min_price, max_price, is_free

    def _format_price(self, value: float) -> str:
        if value == 0:
            return "Free"
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"

    def _resolve_image_url(self, event: Dict[str, Any]) -> str:
        logo = event.get("logo") or {}
        return logo.get("url", "")

    # ---- Destination search fallback -------------------------------------------------

    def _fetch_via_destination(
        self,
        city_key: str,
        *,
        max_pages: int,
        max_results: Optional[int],
    ) -> List[Dict[str, Any]]:
        place_id = self._CITY_TO_PLACE_ID.get(city_key)
        if not place_id:
            logger.info("Destination search does not support city '%s'", city_key)
            return []

        session = self._ensure_destination_session()
        events: List[Dict[str, Any]] = []
        page = 1
        retries = 0

        while page <= max_pages:
            payload = {
                "event_search": {
                    "dates": "current_future",
                    "dedup": True,
                    "places": [place_id],
                    "page": page,
                    "page_size": 20,
                    "online_events_only": False,
                    "languages": ["en"],
                },
                "expand.destination_event": [
                    "primary_venue",
                    "image",
                    "ticket_availability",
                    "event_sales_status",
                    "primary_organizer",
                ],
                "browse_surface": "search",
            }

            try:
                response = session.post(
                    self._DESTINATION_URL,
                    params={"stable_id": self._DESTINATION_STABLE_ID},
                    json=payload,
                    timeout=30,
                )
            except requests.RequestException as exc:
                logger.error("Destination search request failed for '%s': %s", city_key, exc)
                break

            if response.status_code == 401 and retries < 1:
                logger.info("Destination search session expired; refreshing and retrying.")
                self._reset_destination_session()
                session = self._ensure_destination_session()
                retries += 1
                continue

            if not response.ok:
                logger.warning(
                    "Destination search returned %s for '%s': %s",
                    response.status_code,
                    city_key,
                    response.text[:200],
                )
                break

            data = response.json()
            results = (data.get("events", {}) or {}).get("results") or []
            if not results:
                break

            normalized = [self._normalize_destination_event(event) for event in results]
            events.extend(normalized)

            if max_results is not None and len(events) >= max_results:
                return events[:max_results]

            pagination = data.get("pagination", {})
            if not pagination.get("has_more_items"):
                break
            page += 1

        return events

    def _normalize_destination_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        venue = event.get("primary_venue") or {}
        address = venue.get("address") or {}
        organizer = event.get("primary_organizer") or {}
        ticket = event.get("ticket_availability") or {}
        image = event.get("image") or {}

        ticket_min, ticket_max, is_free = self._extract_destination_price_info(ticket)

        return {
            "event_id": str(event.get("eventbrite_event_id") or event.get("id", "")),
            "title": event.get("name", ""),
            "description": event.get("summary") or "",
            "start_datetime": self._combine_date_time(event.get("start_date"), event.get("start_time")),
            "end_datetime": self._combine_date_time(event.get("end_date"), event.get("end_time")),
            "timezone": event.get("timezone", "UTC"),
            "venue_name": venue.get("name", ""),
            "venue_city": address.get("city", ""),
            "venue_country": address.get("country", ""),
            "latitude": self._to_float(address.get("latitude")),
            "longitude": self._to_float(address.get("longitude")),
            "organizer_name": organizer.get("name", ""),
            "organizer_id": str(organizer.get("id", "")),
            "ticket_min_price": ticket_min,
            "ticket_max_price": ticket_max,
            "is_free": is_free,
            "categories": self._extract_destination_categories(event),
            "image_url": image.get("url", ""),
            "event_url": event.get("url", ""),
            "attendee_count": 0,
            "source": self.name,
        }

    def _ensure_destination_session(self) -> requests.Session:
        if self._destination_session is not None:
            return self._destination_session

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json",
        })

        try:
            response = session.get(self._EVENTBRITE_ROOT, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Unable to bootstrap Eventbrite session: %s", exc)
            raise

        csrftoken = session.cookies.get("csrftoken")
        session.headers.update({
            "Referer": self._EVENTBRITE_ROOT,
            "X-Requested-With": "XMLHttpRequest",
        })
        if csrftoken:
            session.headers["X-CSRFToken"] = csrftoken
            session.headers["x-csrftoken"] = csrftoken

        self._destination_session = session
        return session

    def _reset_destination_session(self) -> None:
        self._destination_session = None

    def _extract_destination_price_info(self, ticket: Dict[str, Any]) -> tuple[str, str, bool]:
        minimum = ticket.get("minimum_ticket_price") or {}
        maximum = ticket.get("maximum_ticket_price") or {}
        is_free = bool(ticket.get("is_free", False))

        min_price = self._format_destination_price(minimum.get("major_value"), is_free)
        max_price = self._format_destination_price(maximum.get("major_value"), is_free)

        return min_price, max_price, is_free

    def _format_destination_price(self, raw: Optional[str], is_free: bool) -> str:
        if is_free:
            return "Free"
        if not raw:
            return ""
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return raw
        return self._format_price(value)

    def _combine_date_time(self, date_str: Optional[str], time_str: Optional[str]) -> str:
        if not date_str:
            return ""
        time_component = time_str or "00:00"
        return f"{date_str}T{time_component}"

    def _to_float(self, value: Optional[str]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_destination_categories(self, event: Dict[str, Any]) -> List[str]:
        tags = event.get("tags") or []
        categories: List[str] = []
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            display = tag.get("display_name")
            if display:
                categories.append(display)
        return categories

    def _resolve_city_key(self, city: str) -> str:
        normalized = city.lower().strip()
        normalized = normalized.replace(",", "")
        normalized = normalized.replace("/", " ")
        normalized = normalized.replace("-", " ")
        normalized = " ".join(normalized.split())
        return self._ALIAS_TO_CITY.get(normalized, normalized.replace(" ", "_"))


