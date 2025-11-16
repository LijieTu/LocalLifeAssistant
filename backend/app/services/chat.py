#!/usr/bin/env python3
"""
Chat orchestration service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..api.schemas import ChatRequest
from ..cache_manager import CacheManager
from ..conversation_storage import ConversationStorage
from ..event_service import EventCrawler
from ..extraction_service import ExtractionService, UserPreferences
from ..search_service import SearchService
from ..usage_tracker import UsageTracker

logger = logging.getLogger(__name__)


@dataclass
class ChatOutcome:
    message: str
    recommendations: List[Dict[str, Any]]
    cache_used: bool
    cache_age_hours: Optional[float]
    extracted_preferences: Optional[UserPreferences]
    extraction_summary: Optional[str]
    usage_stats: Optional[Dict[str, Any]]
    trial_exceeded: bool
    conversation_id: str


class ChatService:
    """Co-ordinates chat flow between user-facing API and backend services."""

    def __init__(
        self,
        *,
        cache_manager: CacheManager,
        event_crawler: EventCrawler,
        search_service: SearchService,
        extraction_service: ExtractionService,
        usage_tracker: UsageTracker,
        conversation_storage: ConversationStorage,
    ) -> None:
        self.cache_manager = cache_manager
        self.event_crawler = event_crawler
        self.search_service = search_service
        self.extraction_service = extraction_service
        self.usage_tracker = usage_tracker
        self.conversation_storage = conversation_storage

    async def handle_chat(self, request: ChatRequest) -> ChatOutcome:
        user_id = request.user_id
        conversation_id = request.conversation_id
        usage_stats: Optional[Dict[str, Any]] = None

        if user_id.startswith("user_"):
            if self.usage_tracker.check_trial_limit(user_id):
                limit = self.usage_tracker.trial_limit
                message = (
                    f"🔒 You've reached your free trial limit of {limit} interactions! "
                    "Please register to continue using our service and keep your conversation history."
                )
                return ChatOutcome(
                    message=message,
                    recommendations=[],
                    cache_used=False,
                    cache_age_hours=None,
                    extracted_preferences=None,
                    extraction_summary=None,
                    usage_stats=self.usage_tracker.get_usage(user_id),
                    trial_exceeded=True,
                    conversation_id="temp",
                )
            usage_stats = self.usage_tracker.increment_usage(user_id)

        if not conversation_id:
            conversation_id = self.conversation_storage.create_conversation(
                user_id,
                {"llm_provider": request.llm_provider},
            )

        stored_preferences, history = self._lookup_stored_preferences(user_id, conversation_id)
        extracted_preferences = self._extract_preferences(request, stored_preferences, history)

        self.conversation_storage.save_message(
            user_id,
            conversation_id,
            {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
            },
        )

        city, location_provided = self._determine_city(
            request,
            extracted_preferences,
            stored_preferences.location,
        )
        if request.is_initial_response and not location_provided:
            prompt = (
                "I'd be happy to help you find events! To give you the best recommendations, "
                "could you please tell me which city or area you're interested in? "
                "(e.g., 'New York', 'Los Angeles', 'Chicago', or a zipcode)"
            )
            return ChatOutcome(
                message=prompt,
                recommendations=[],
                cache_used=False,
                cache_age_hours=None,
                extracted_preferences=extracted_preferences,
                extraction_summary=None,
                usage_stats=usage_stats,
                trial_exceeded=False,
                conversation_id=conversation_id,
            )

        events, cache_used, cache_age_hours = self._fetch_events(city)
        ranked_events = await self._rank_events(request, events, extracted_preferences)

        recommendations = self._format_recommendations(city, ranked_events, cache_used)
        response_message = self._compose_response(city, ranked_events, location_provided)
        extraction_summary = self._build_extraction_summary(extracted_preferences)

        self._record_assistant_response(
            user_id=user_id,
            conversation_id=conversation_id,
            message=response_message,
            recommendations=recommendations,
            extracted_preferences=extracted_preferences,
            cache_used=cache_used,
            cache_age_hours=cache_age_hours,
        )

        return ChatOutcome(
            message=response_message,
            recommendations=recommendations,
            cache_used=cache_used,
            cache_age_hours=cache_age_hours,
            extracted_preferences=extracted_preferences,
            extraction_summary=extraction_summary,
            usage_stats=usage_stats,
            trial_exceeded=False,
            conversation_id=conversation_id,
        )

    def _extract_preferences(
        self,
        request: ChatRequest,
        stored_preferences: "StoredPreferences",
        history: "ConversationHistory",
    ) -> Optional[UserPreferences]:
        combined_history: List[Dict[str, str]] = list(history.messages)

        if request.conversation_history:
            seen = {(msg.get("role"), msg.get("content")) for msg in combined_history}
            for msg in request.conversation_history[-6:]:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                content = msg.get("content")
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    continue
                key = (role, content)
                if key not in seen:
                    combined_history.append({"role": role, "content": content})
                    seen.add(key)

            if len(combined_history) > 6:
                combined_history = combined_history[-6:]

        prefs = self.extraction_service.extract_user_preferences(
            request.message,
            conversation_history=combined_history,
        )
        logger.info("LLM raw preferences: %s", prefs)

        if stored_preferences.event_type and (not prefs.event_type or prefs.event_type == "none"):
            prefs.event_type = stored_preferences.event_type
        if stored_preferences.date and (not prefs.date or prefs.date == "none"):
            prefs.date = stored_preferences.date
        if stored_preferences.time and (not prefs.time or prefs.time == "none"):
            prefs.time = stored_preferences.time
        latest_city: Optional[str] = None
        history_for_city: List[Dict[str, Any]] = []
        if history.messages:
            history_for_city.extend(history.messages)
        if request.conversation_history:
            history_for_city.extend(request.conversation_history)
        history_for_city.append({"role": "user", "content": request.message})
        logger.info(
            "City detection history (latest first): %s",
            [msg.get("content") for msg in reversed(history_for_city) if isinstance(msg, dict)],
        )

        for message in reversed(history_for_city):
            if not isinstance(message, dict):
                continue
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            history_city = self.extraction_service.extract_location_from_query(content)
            if history_city:
                latest_city = history_city
                break

        if latest_city:
            prefs.location = latest_city
        elif stored_preferences.location and (not prefs.location or prefs.location == "none"):
            prefs.location = stored_preferences.location

        logger.info("Preferences after merging history/stored values: %s", prefs)

        if request.is_initial_response:
            logger.info("Initial response detected, extracted preferences: %s", prefs)
        else:
            logger.info("Follow-up extraction result: %s", prefs)
        return prefs

    def _determine_city(
        self,
        request: ChatRequest,
        extracted_preferences: Optional[UserPreferences],
        stored_location: Optional[str],
    ) -> tuple[str, bool]:
        if extracted_preferences and extracted_preferences.location and extracted_preferences.location != "none":
            city = extracted_preferences.location.lower()
            logger.info("Using city from extracted preferences: %s", city)
            return city, True

        query_city = self.extraction_service.extract_location_from_query(request.message)
        if query_city:
            logger.info("Using city from query extraction: %s", query_city)
            if extracted_preferences:
                extracted_preferences.location = query_city
            return query_city.lower(), True

        if stored_location:
            logger.info("Using stored location from conversation: %s", stored_location)
            return stored_location.lower(), True

        logger.info("No city found, defaulting to New York")
        return "new york", False

    def _fetch_events(self, city: str) -> tuple[List[Dict[str, Any]], bool, Optional[float]]:
        cached_events = self.cache_manager.get_cached_events(city, self.event_crawler)
        events = cached_events or []
        cache_age_hours = self.cache_manager.get_cache_age(city) if events else None
        cache_used = bool(cache_age_hours and cache_age_hours > 0)
        if cache_used:
            logger.info("Using cached events for %s (age: %.1fh)", city, cache_age_hours)
        elif events:
            logger.info("Fetched %d fresh events for %s", len(events), city)
        else:
            logger.warning("Failed to get any events for %s", city)
        return events, cache_used, cache_age_hours

    def _lookup_stored_preferences(
        self,
        user_id: str,
        conversation_id: str,
    ) -> tuple["StoredPreferences", "ConversationHistory"]:
        stored = StoredPreferences()
        history = ConversationHistory()
        try:
            conversation = self.conversation_storage.get_conversation(user_id, conversation_id)
            if not conversation:
                return stored, history

            for message in reversed(conversation.get("messages", [])):
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                content = message.get("content")
                if role in {"user", "assistant"} and isinstance(content, str):
                    history.prepend(role, content)

                prefs = message.get("extracted_preferences")
                if not isinstance(prefs, dict):
                    continue

                location = prefs.get("location")
                if location and location.lower() != "none" and not stored.location:
                    stored.location = location

                event_type = prefs.get("event_type")
                if event_type and event_type.lower() != "none" and not stored.event_type:
                    stored.event_type = event_type

                date = prefs.get("date")
                if date and date.lower() != "none" and not stored.date:
                    stored.date = date

                time = prefs.get("time")
                if time and time.lower() != "none" and not stored.time:
                    stored.time = time

                if stored.is_complete:
                    break
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Unable to load stored preferences for %s: %s", conversation_id, exc)
        return stored, history

    async def _rank_events(
        self,
        request: ChatRequest,
        events: List[Dict[str, Any]],
        extracted_preferences: Optional[UserPreferences],
    ) -> List[Dict[str, Any]]:
        if extracted_preferences:
            user_preferences_dict = {
                "location": extracted_preferences.location,
                "date": extracted_preferences.date,
                "time": extracted_preferences.time,
                "event_type": extracted_preferences.event_type,
            }
        else:
            user_preferences_dict = None

        ranked = await self.search_service.intelligent_event_search(
            request.message,
            events,
            user_preferences=user_preferences_dict,
        )
        logger.info("LLM search returned %d events", len(ranked))
        return ranked

    def _format_recommendations(
        self,
        city: str,
        events: List[Dict[str, Any]],
        cache_used: bool,
    ) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []
        for event in events:
            recommendations.append(
                {
                    "type": "event",
                    "data": {
                        **event,
                        "source": "cached" if cache_used else "realtime",
                    },
                    "relevance_score": event.get("relevance_score", 0.5),
                    "explanation": f"Event in {city.title()}: {event.get('title', 'Unknown Event')}",
                }
            )
        if events:
            first_event = events[0]
            logger.info("First ranked event scores: %s", first_event.get("llm_scores", "None"))
        return recommendations

    def _compose_response(self, city: str, events: List[Dict[str, any]], location_provided: bool) -> str:
        location_note = ""
        if not location_provided and city == "new york":
            location_note = " (I couldn't determine your location, so I'm defaulting to New York)"

        if events:
            return (
                f"🎉 Found {len(events)} events in {city.title()} that match your search!"
                f"{location_note} Check out the recommendations below ↓"
            )
        return (
            f"😔 I couldn't find any events in {city.title()} matching your query."
            f"{location_note} Try asking about 'fashion events', 'music concerts', 'halloween parties', or 'free events'."
        )

    def _build_extraction_summary(self, extracted_preferences: Optional[UserPreferences]) -> Optional[str]:
        if not extracted_preferences:
            return None

        summary_parts: List[str] = []
        if extracted_preferences.location and extracted_preferences.location != "none":
            summary_parts.append(f"📍 {extracted_preferences.location}")
        if extracted_preferences.date and extracted_preferences.date != "none":
            summary_parts.append(f"📅 {extracted_preferences.date}")
        if extracted_preferences.time and extracted_preferences.time != "none":
            summary_parts.append(f"🕐 {extracted_preferences.time}")
        if extracted_preferences.event_type and extracted_preferences.event_type != "none":
            summary_parts.append(f"🎭 {extracted_preferences.event_type}")

        return " • ".join(summary_parts) if summary_parts else None

    def _record_assistant_response(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message: str,
        recommendations: List[Dict[str, Any]],
        extracted_preferences: Optional[UserPreferences],
        cache_used: bool,
        cache_age_hours: Optional[float],
    ) -> None:
        self.conversation_storage.save_message(
            user_id,
            conversation_id,
            {
                "role": "assistant",
                "content": message,
                "timestamp": datetime.now().isoformat(),
                "recommendations": recommendations,
                "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
                "cache_used": cache_used,
                "cache_age_hours": cache_age_hours,
            },
        )
        self.conversation_storage.update_metadata(
            user_id,
            conversation_id,
            {"last_message_at": datetime.now().isoformat()},
        )


@dataclass
class StoredPreferences:
    location: Optional[str] = None
    event_type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        return all([self.location, self.event_type, self.date, self.time])


class ConversationHistory:
    def __init__(self, window: int = 10) -> None:
        self._window = window
        self.messages: List[Dict[str, str]] = []

    def prepend(self, role: str, content: str) -> None:
        self.messages.insert(0, {"role": role, "content": content})
        if len(self.messages) > self._window:
            self.messages = self.messages[-self._window:]


