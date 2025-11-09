#!/usr/bin/env python3
"""
Service container for shared backend dependencies.
"""

from __future__ import annotations

from functools import lru_cache

from .settings import Settings, get_settings
from ..cache_manager import CacheManager
from ..conversation_storage import ConversationStorage
from ..event_service import EventCrawler
from ..extraction_service import ExtractionService
from ..search_service import SearchService
from ..services.chat import ChatService
from ..services.events import EventAggregator, create_default_aggregator
from ..usage_tracker import UsageTracker
from ..user_manager import UserManager


class ServiceContainer:
    """Lazily initialised service container."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._event_crawler: EventCrawler | None = None
        self._event_aggregator: EventAggregator | None = None
        self._chat_service: ChatService | None = None
        self._cache_manager: CacheManager | None = None
        self._search_service: SearchService | None = None
        self._extraction_service: ExtractionService | None = None
        self._usage_tracker: UsageTracker | None = None
        self._conversation_storage: ConversationStorage | None = None
        self._user_manager: UserManager | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def event_crawler(self) -> EventCrawler:
        if self._event_crawler is None:
            self._event_crawler = EventCrawler(
                providers=self.event_aggregator.providers,
            )
        return self._event_crawler

    @property
    def event_aggregator(self) -> EventAggregator:
        if self._event_aggregator is None:
            self._event_aggregator = create_default_aggregator()
        return self._event_aggregator

    @property
    def cache_manager(self) -> CacheManager:
        if self._cache_manager is None:
            self._cache_manager = CacheManager(ttl_hours=self._settings.cache_ttl_hours)
        return self._cache_manager

    @property
    def chat_service(self) -> ChatService:
        if self._chat_service is None:
            self._chat_service = ChatService(
                cache_manager=self.cache_manager,
                event_crawler=self.event_crawler,
                search_service=self.search_service,
                extraction_service=self.extraction_service,
                usage_tracker=self.usage_tracker,
                conversation_storage=self.conversation_storage,
            )
        return self._chat_service

    @property
    def search_service(self) -> SearchService:
        if self._search_service is None:
            self._search_service = SearchService()
        return self._search_service

    @property
    def extraction_service(self) -> ExtractionService:
        if self._extraction_service is None:
            self._extraction_service = ExtractionService()
        return self._extraction_service

    @property
    def usage_tracker(self) -> UsageTracker:
        if self._usage_tracker is None:
            self._usage_tracker = UsageTracker()
        return self._usage_tracker

    @property
    def conversation_storage(self) -> ConversationStorage:
        if self._conversation_storage is None:
            self._conversation_storage = ConversationStorage()
        return self._conversation_storage

    @property
    def user_manager(self) -> UserManager:
        if self._user_manager is None:
            self._user_manager = UserManager()
        return self._user_manager


@lru_cache(maxsize=1)
def get_service_container() -> ServiceContainer:
    """Return the shared service container instance."""
    return ServiceContainer(get_settings())


