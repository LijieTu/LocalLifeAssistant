#!/usr/bin/env python3
"""
Chat and conversation related endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ...core.container import ServiceContainer, get_service_container
from ..schemas import ChatRequest, ChatResponse, CreateConversationRequest, MigrateConversationsRequest

router = APIRouter()

logger = logging.getLogger(__name__)


def get_container() -> ServiceContainer:
    return get_service_container()


async def stream_chat_response(
    request: ChatRequest,
    container: ServiceContainer,
):
    """Generator function for streaming chat responses."""
    logger.info("Streaming chat request: %s", request.message)
    user_id = request.user_id
    usage_tracker = container.usage_tracker
    cache_manager = container.cache_manager
    event_crawler = container.event_crawler
    search_service = container.search_service
    extraction_service = container.extraction_service
    conversation_storage = container.conversation_storage

    if user_id.startswith("user_"):
        if usage_tracker.check_trial_limit(user_id):
            trial_limit = usage_tracker.trial_limit
            trial_message = (
                "🔒 You've reached your free trial limit of "
                f"{trial_limit} interactions! Please register to continue using our service "
                "and keep your conversation history."
            )
            yield f"data: {json.dumps({'type': 'message', 'content': trial_message, 'trial_exceeded': True})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
            return

    if user_id.startswith("user_"):
        usage_stats = usage_tracker.increment_usage(user_id)
    else:
        usage_stats = None

    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = conversation_storage.create_conversation(
            user_id,
            {"llm_provider": request.llm_provider},
        )

    extracted_preferences = None
    if request.is_initial_response:
        logger.info("Initial response detected, extracting user preferences")
        extracted_preferences = extraction_service.extract_user_preferences(request.message)
        logger.info("Extracted preferences: %s", extracted_preferences)
    else:
        logger.info("Non-initial response detected")

    city: Optional[str] = None
    location_provided = False

    if extracted_preferences and extracted_preferences.location and extracted_preferences.location != "none":
        city = extracted_preferences.location.lower()
        location_provided = True
        logger.info("Using city from extracted preferences: %s", city)

    if not city:
        query_city = extraction_service.extract_location_from_query(request.message)
        if query_city:
            city = query_city.lower()
            location_provided = True
            if extracted_preferences:
                extracted_preferences.location = query_city
            else:
                from ...extraction_service import UserPreferences

                extracted_preferences = UserPreferences(location=query_city)
            logger.info("Using city from query extraction: %s, updated extracted_preferences", city)

    if request.is_initial_response:
        prefs_dict = extracted_preferences.dict() if extracted_preferences else None
        logger.info("Saving initial user message with extracted_preferences: %s", prefs_dict)
        conversation_storage.save_message(
            user_id,
            conversation_id,
            {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "extracted_preferences": prefs_dict,
            },
        )
        logger.info(
            "Saved user message for conversation %s, location in prefs: %s",
            conversation_id,
            prefs_dict.get("location") if prefs_dict else "None",
        )

    if request.is_initial_response and not location_provided:
        logger.info("No location provided in initial response, asking user for location")
        location_message = (
            "I'd be happy to help you find events! To give you the best recommendations, "
            "could you please tell me which city or area you're interested in? "
            "(e.g., 'New York', 'Los Angeles', 'Chicago', or a zipcode)"
        )
        yield f"data: {json.dumps({'type': 'message', 'content': location_message})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"
        return

    event_type_provided = (
        extracted_preferences
        and extracted_preferences.event_type
        and extracted_preferences.event_type != "none"
    )

    if request.is_initial_response and location_provided and not event_type_provided:
        logger.info("Location provided but no event type in initial response, asking for event type")
        follow_up_message = "Great! What kind of events are you interested in?"
        yield f"data: {json.dumps({'type': 'message', 'content': follow_up_message, 'location_processed': True, 'usage_stats': usage_stats, 'trial_exceeded': False, 'conversation_id': conversation_id})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

        conversation_storage.save_message(
            user_id,
            conversation_id,
            {
                "role": "assistant",
                "content": follow_up_message,
                "timestamp": datetime.now().isoformat(),
                "recommendations": [],
                "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
            },
        )
        return

    if not request.is_initial_response:
        stored_location = None
        try:
            logger.info(
                "Retrieving conversation %s for user %s (anonymous: %s)",
                conversation_id,
                user_id,
                user_id.startswith("user_"),
            )
            conversation = conversation_storage.get_conversation(user_id, conversation_id)
            if conversation:
                logger.info(
                    "Conversation found, message count: %d",
                    len(conversation.get("messages", [])),
                )
                if conversation.get("messages"):
                    for idx, msg in enumerate(conversation.get("messages", [])):
                        if isinstance(msg, dict):
                            msg_role = msg.get("role")
                            msg_content = msg.get("content", "")[:50]
                            stored_prefs = msg.get("extracted_preferences")
                            logger.info(
                                "Message %d: role=%s, content='%s...', has_prefs=%s",
                                idx,
                                msg_role,
                                msg_content,
                                stored_prefs is not None,
                            )
                            if stored_prefs and isinstance(stored_prefs, dict):
                                location_value = stored_prefs.get("location")
                                logger.info("  extracted_preferences dict: location=%s", location_value)
                                if location_value and location_value != "none":
                                    stored_location = location_value
                                    logger.info("✓ Found stored location in message %d: %s", idx, stored_location)
                                    break
        except Exception as exc:
            logger.error(
                "Could not retrieve conversation to get stored location: %s",
                exc,
                exc_info=True,
            )

        if not extracted_preferences:
            extracted_preferences = extraction_service.extract_user_preferences(request.message)
        else:
            current_preferences = extraction_service.extract_user_preferences(request.message)
            if current_preferences:
                if current_preferences.event_type and current_preferences.event_type != "none":
                    extracted_preferences.event_type = current_preferences.event_type
                if current_preferences.date and current_preferences.date != "none":
                    extracted_preferences.date = current_preferences.date
                if current_preferences.time and current_preferences.time != "none":
                    extracted_preferences.time = current_preferences.time

        event_type_provided = (
            extracted_preferences
            and extracted_preferences.event_type
            and extracted_preferences.event_type != "none"
        )

        if stored_location:
            city = stored_location.lower()
            location_provided = True
            if extracted_preferences:
                extracted_preferences.location = stored_location
            else:
                from ...extraction_service import UserPreferences

                extracted_preferences = UserPreferences(location=stored_location)
            logger.info("Using stored location: %s", stored_location)

        if not location_provided:
            logger.warning("Non-initial response but no location found")
            location_message = (
                "I need to know which city you're interested in. Could you please tell me the city or area?"
            )
            yield f"data: {json.dumps({'type': 'message', 'content': location_message})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
            conversation_storage.save_message(
                user_id,
                conversation_id,
                {
                    "role": "user",
                    "content": request.message,
                    "timestamp": datetime.now().isoformat(),
                    "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
                },
            )
            return

        if not event_type_provided:
            logger.warning("Non-initial response but no event type found")
            event_type_message = "What kind of events are you interested in?"
            yield f"data: {json.dumps({'type': 'message', 'content': event_type_message})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
            conversation_storage.save_message(
                user_id,
                conversation_id,
                {
                    "role": "user",
                    "content": request.message,
                    "timestamp": datetime.now().isoformat(),
                    "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
                },
            )
            return

        conversation_storage.save_message(
            user_id,
            conversation_id,
            {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
            },
        )

    if not city:
        city = "new york"
        logger.info("No city found, defaulting to New York")
        if not request.is_initial_response:
            logger.info("Informing user that we're defaulting to New York")

    logger.info(
        "Final city decision: %s, Event type: %s",
        city,
        extracted_preferences.event_type if extracted_preferences else "none",
    )

    yield f"data: {json.dumps({'type': 'status', 'content': f'Searching for events in {city.title()}...'})}\n\n"
    await asyncio.sleep(0.3)

    cached_events = cache_manager.get_cached_events(city, event_crawler)
    cache_age_hours = cache_manager.get_cache_age(city)

    if cached_events:
        events = cached_events
        if cache_age_hours is not None and cache_age_hours > 0:
            logger.info("Using cached events for %s (age: %.1fh)", city, cache_age_hours)
            cache_used = True
            yield f"data: {json.dumps({'type': 'status', 'content': f'Found cached events for {city.title()} (from {cache_age_hours:.1f}h ago)'})}\n\n"
        else:
            logger.info("Fetched %d fresh events for %s", len(events), city)
            cache_used = False
            yield f"data: {json.dumps({'type': 'status', 'content': f'Found {len(events)} fresh events for {city.title()}'})}\n\n"
    else:
        logger.warning("Failed to get any events for %s", city)
        events = []
        cache_used = False
        cache_age_hours = None

    analysis_messages = [
        "Analyzing events with AI to find the best matches...",
        "Using AI to rank and filter the most relevant events...",
    ]

    logger.info("Starting LLM search for query: '%s' with %d events", request.message, len(events))

    user_preferences_dict: Optional[Dict[str, Optional[str]]] = None
    if extracted_preferences:
        user_preferences_dict = {
            "location": extracted_preferences.location,
            "date": extracted_preferences.date,
            "time": extracted_preferences.time,
            "event_type": extracted_preferences.event_type,
        }

    async def ai_processing():
        return await search_service.intelligent_event_search(
            request.message,
            events,
            user_preferences=user_preferences_dict,
        )

    ai_task = asyncio.create_task(ai_processing())

    idx = 0
    while not ai_task.done():
        message = analysis_messages[idx % 2]
        yield f"data: {json.dumps({'type': 'status', 'content': message})}\n\n"
        await asyncio.sleep(1.5)
        logger.info("AI processing message: %s", message)
        idx += 1

    top_events = await ai_task
    logger.info("LLM search returned %d events", len(top_events))

    if top_events:
        first_event = top_events[0]
        logger.info("First event has llm_scores: %s", first_event.get("llm_scores", "None"))
        logger.info("First event relevance_score: %s", first_event.get("relevance_score", "None"))

    extraction_summary = None
    if extracted_preferences:
        summary_parts = []
        if extracted_preferences.location and extracted_preferences.location != "none":
            summary_parts.append(f"📍 {extracted_preferences.location}")
        if extracted_preferences.date and extracted_preferences.date != "none":
            summary_parts.append(f"📅 {extracted_preferences.date}")
        if extracted_preferences.time and extracted_preferences.time != "none":
            summary_parts.append(f"🕐 {extracted_preferences.time}")
        if extracted_preferences.event_type and extracted_preferences.event_type != "none":
            summary_parts.append(f"🎭 {extracted_preferences.event_type}")
        if summary_parts:
            extraction_summary = " • ".join(summary_parts)

    location_note = ""
    if not location_provided and city == "new york":
        location_note = " (I couldn't determine your location, so I'm defaulting to New York)"

    if top_events:
        response_message = (
            f"🎉 Found {len(top_events)} events in {city.title()} that match your search!"
            f"{location_note} Check out the recommendations below ↓"
        )
    else:
        response_message = (
            f"😔 I couldn't find any events in {city.title()} matching your query."
            f"{location_note} Try asking about 'fashion events', 'music concerts', 'halloween parties', or 'free events'."
        )

    location_just_processed = request.is_initial_response and location_provided

    yield f"data: {json.dumps({'type': 'message', 'content': response_message, 'extraction_summary': extraction_summary, 'usage_stats': usage_stats, 'trial_exceeded': False, 'conversation_id': conversation_id, 'location_processed': location_just_processed})}\n\n"

    yield f"data: {json.dumps({'type': 'status', 'content': f'Preparing {len(top_events)} recommendations...'})}\n\n"
    await asyncio.sleep(0.3)

    formatted_recommendations = []
    for event in top_events:
        formatted_rec = {
            "type": "event",
            "data": {
                **event,
                "source": "cached" if cache_used else "realtime",
            },
            "relevance_score": event.get("relevance_score", 0.5),
            "explanation": f"Event in {city.title()}: {event.get('title', 'Unknown Event')}",
        }
        formatted_recommendations.append(formatted_rec)
        yield f"data: {json.dumps({'type': 'recommendation', 'data': formatted_rec})}\n\n"
        await asyncio.sleep(0.2)

    conversation_storage.save_message(
        user_id,
        conversation_id,
        {
            "role": "assistant",
            "content": response_message,
            "timestamp": datetime.now().isoformat(),
            "recommendations": formatted_recommendations,
            "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
            "cache_used": cache_used,
            "cache_age_hours": cache_age_hours,
        },
    )

    conversation_storage.update_metadata(
        user_id,
        conversation_id,
        {"last_message_at": datetime.now().isoformat()},
    )

    yield "data: {\"type\": \"done\"}\n\n"


@router.post("/api/chat", response_model=ChatResponse)
async def smart_cached_chat(
    request: ChatRequest,
    container: ServiceContainer = Depends(get_container),
):
    """Smart cached chat endpoint."""
    try:
        outcome = await container.chat_service.handle_chat(request)
        return ChatResponse(
            message=outcome.message,
            recommendations=outcome.recommendations,
            llm_provider_used=request.llm_provider,
            cache_used=outcome.cache_used,
            cache_age_hours=outcome.cache_age_hours,
            extracted_preferences=outcome.extracted_preferences,
            extraction_summary=outcome.extraction_summary,
            usage_stats=outcome.usage_stats,
            trial_exceeded=outcome.trial_exceeded,
            conversation_id=outcome.conversation_id,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error in smart cached chat: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing chat request: {exc}") from exc


@router.post("/api/chat/stream")
async def stream_chat(
    request: ChatRequest,
    container: ServiceContainer = Depends(get_container),
):
    """Streaming chat endpoint using Server-Sent Events."""
    async def event_stream():
        async for chunk in stream_chat_response(request, container):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@router.get("/api/usage/{user_id}")
async def get_user_usage(
    user_id: str,
    container: ServiceContainer = Depends(get_container),
):
    """Get usage statistics for a user."""
    usage_tracker = container.usage_tracker
    return usage_tracker.get_usage(user_id)


@router.post("/api/auth/register")
async def register_with_token(
    request: Dict[str, str] = Body(...),
    container: ServiceContainer = Depends(get_container),
):
    """Register a Firebase-authenticated user and migrate their conversation history."""
    user_manager = container.user_manager
    conversation_storage = container.conversation_storage
    usage_tracker = container.usage_tracker

    token = request.get("token")
    anonymous_user_id = request.get("anonymous_user_id")

    if not token:
        raise HTTPException(status_code=400, detail="Firebase token required")

    try:
        user_data = user_manager.authenticate_with_token(token)
        real_user_id = user_data["user_id"]

        migrated_count = conversation_storage.migrate_user_conversations(
            anonymous_user_id,
            real_user_id,
        )

        usage_tracker.mark_registered(anonymous_user_id, real_user_id)

        logger.info("User registered with Firebase: %s -> %s", user_data["email"], real_user_id)

        return {
            "success": True,
            "user_id": real_user_id,
            "migrated_conversations": migrated_count,
            "message": f"Registration successful! {migrated_count} conversations migrated.",
        }
    except ValueError as exc:
        logger.error("Firebase registration error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Firebase registration error (Unexpected): %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}") from exc


@router.post("/api/auth/verify")
async def verify_auth_token(
    request: Dict[str, str] = Body(...),
    container: ServiceContainer = Depends(get_container),
):
    """Verify Firebase Auth token."""
    user_manager = container.user_manager

    token = request.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="No authentication token provided")

    try:
        user_data = user_manager.authenticate_with_token(token)
        return {
            "success": True,
            "user_id": user_data.get("user_id"),
            "email": user_data.get("email"),
            "name": user_data.get("name"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/api/users/migrate-conversations")
async def migrate_conversations(
    request: MigrateConversationsRequest = Body(...),
    container: ServiceContainer = Depends(get_container),
):
    """Migrate conversations from anonymous user to registered user."""
    conversation_storage = container.conversation_storage
    try:
        migrated_count = conversation_storage.migrate_user_conversations(
            request.anonymous_user_id,
            request.real_user_id,
        )
        return {
            "success": True,
            "migrated_conversations": migrated_count,
        }
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Conversation migration failed: %s", exc)
        return {"success": False, "error": str(exc)}


@router.post("/api/conversations/create")
async def create_conversation(
    request: CreateConversationRequest = Body(...),
    container: ServiceContainer = Depends(get_container),
):
    """Create a new conversation for a user."""
    conversation_storage = container.conversation_storage
    conversation_id = conversation_storage.create_conversation(request.user_id, request.metadata)
    return {"conversation_id": conversation_id}


@router.get("/api/conversations/{user_id}/{conversation_id}")
async def get_conversation(
    user_id: str,
    conversation_id: str,
    container: ServiceContainer = Depends(get_container),
):
    """Get specific conversation for a user."""
    conversation_storage = container.conversation_storage
    try:
        conversation = conversation_storage.get_conversation(user_id, conversation_id)
        return conversation
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@router.get("/api/conversations/{user_id}/list")
async def list_user_conversations(
    user_id: str,
    limit: int = 50,
    container: ServiceContainer = Depends(get_container),
):
    """List all conversations for a specific user."""
    conversation_storage = container.conversation_storage
    conversations = conversation_storage.list_user_conversations(user_id, limit)
    return {"conversations": conversations}


@router.delete("/api/conversations/{user_id}/{conversation_id}")
async def delete_conversation(
    user_id: str,
    conversation_id: str,
    container: ServiceContainer = Depends(get_container),
):
    """Delete a conversation."""
    conversation_storage = container.conversation_storage
    try:
        conversation_storage.delete_conversation(user_id, conversation_id)
        return {"success": True}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


