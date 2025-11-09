#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from backend.app.api.schemas import ChatRequest
from backend.app.extraction_service import UserPreferences
from backend.app.services.chat import ChatService


class FakeCacheManager:
    def __init__(self, events: List[Dict[str, Any]], age: float = 1.0):
        self.events = events
        self.age = age
        self.queried_city: Optional[str] = None

    def get_cached_events(self, city: str, event_crawler) -> List[Dict[str, Any]]:
        self.queried_city = city
        return self.events

    def get_cache_age(self, city: str) -> Optional[float]:
        return self.age


class FakeEventCrawler:
    def fetch_events_by_city(self, city: str, max_pages: int = 3):
        return []


class FakeSearchService:
    async def intelligent_event_search(self, query: str, events: List[Dict[str, Any]], user_preferences=None):
        return events


class FakeExtractionService:
    def __init__(self, location: Optional[str] = None):
        self.location = location

    def extract_user_preferences(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> UserPreferences:
        return UserPreferences(
            location=self.location or "none",
            date="none",
            time="none",
            event_type="art",
        )

    def extract_location_from_query(self, message: str) -> Optional[str]:
        return self.location


class FakeUsageTracker:
    def __init__(self, limit_reached: bool = False):
        self.limit_reached = limit_reached
        self.trial_limit = 3

    def check_trial_limit(self, user_id: str) -> bool:
        return self.limit_reached

    def increment_usage(self, user_id: str) -> Dict[str, Any]:
        return {"count": 1}

    def get_usage(self, user_id: str) -> Dict[str, Any]:
        return {"count": 1}

    def mark_registered(self, anonymous_user_id: str, real_user_id: str) -> None:
        pass


class FakeConversationStorage:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}

    def create_conversation(self, user_id: str, metadata: Dict[str, Any]) -> str:
        return "conversation-1"

    def save_message(self, user_id: str, conversation_id: str, message: Dict[str, Any]) -> None:
        self.messages.append(message)

    def update_metadata(self, user_id: str, conversation_id: str, metadata: Dict[str, Any]) -> None:
        self.metadata.update(metadata)

    def migrate_user_conversations(self, anonymous_user_id: str, real_user_id: str) -> int:
        return 0

    def get_conversation(self, user_id: str, conversation_id: str):
        return {"messages": self.messages}

    def list_user_conversations(self, user_id: str, limit: int):
        return []

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        pass


@pytest.mark.asyncio
async def test_chat_service_returns_recommendations() -> None:
    events = [{"title": "Gallery Opening", "relevance_score": 0.9}]
    chat_service = ChatService(
        cache_manager=FakeCacheManager(events),
        event_crawler=FakeEventCrawler(),
        search_service=FakeSearchService(),
        extraction_service=FakeExtractionService(location="San Francisco"),
        usage_tracker=FakeUsageTracker(limit_reached=False),
        conversation_storage=FakeConversationStorage(),
    )

    request = ChatRequest(
        message="Show me art events in San Francisco",
        llm_provider="openai",
        user_id="user_123",
        is_initial_response=True,
    )

    outcome = await chat_service.handle_chat(request)

    assert outcome.trial_exceeded is False
    assert outcome.cache_used is True
    assert len(outcome.recommendations) == 1
    assert "San Francisco" in outcome.message


@pytest.mark.asyncio
async def test_chat_service_respects_trial_limit() -> None:
    chat_service = ChatService(
        cache_manager=FakeCacheManager([]),
        event_crawler=FakeEventCrawler(),
        search_service=FakeSearchService(),
        extraction_service=FakeExtractionService(location=None),
        usage_tracker=FakeUsageTracker(limit_reached=True),
        conversation_storage=FakeConversationStorage(),
    )

    request = ChatRequest(
        message="hello",
        llm_provider="openai",
        user_id="user_999",
        is_initial_response=True,
    )

    outcome = await chat_service.handle_chat(request)

    assert outcome.trial_exceeded is True
    assert outcome.conversation_id == "temp"
    assert "free trial limit" in outcome.message


