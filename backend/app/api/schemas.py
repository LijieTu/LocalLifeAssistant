#!/usr/bin/env python3
"""
Pydantic schemas for API requests and responses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ..extraction_service import UserPreferences


class ChatRequest(BaseModel):
    message: str
    conversation_history: List[Dict[str, Any]] = []
    llm_provider: str = "openai"
    user_preferences: Optional[UserPreferences] = None
    is_initial_response: bool = False
    user_id: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    recommendations: List[Dict[str, Any]] = []
    llm_provider_used: str
    cache_used: bool = False
    cache_age_hours: Optional[float] = None
    extracted_preferences: Optional[UserPreferences] = None
    extraction_summary: Optional[str] = None
    usage_stats: Optional[Dict[str, Any]] = None
    trial_exceeded: bool = False
    conversation_id: str


class CreateConversationRequest(BaseModel):
    user_id: str
    metadata: Optional[Dict[str, Any]] = None


class MigrateConversationsRequest(BaseModel):
    anonymous_user_id: str
    real_user_id: str


