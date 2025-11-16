#!/usr/bin/env python3
"""
Smart Cached RAG Local Life Assistant
Combines real-time fetching with intelligent city-based caching
"""

import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Response, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import json
import asyncio
from dotenv import load_dotenv

from .firebase_config import db
from .event_service import EventCrawler
from .cache_manager import CacheManager
from .search_service import SearchService
from .extraction_service import ExtractionService, UserPreferences
from .usage_tracker import UsageTracker
from .conversation_storage import ConversationStorage
from .user_manager import UserManager
from .api.routers import events as events_router

# Load environment variables from .env file
load_dotenv('../.env') or load_dotenv('.env') or load_dotenv('/app/.env')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Smart Cached RAG Local Life Assistant",
    version="2.1.0",
    description="""
    AI-powered local life assistant with event search API.
    
    ## Features
    - 🤖 Chat interface with AI recommendations
    - 🎉 Event search across multiple providers
    - 🔐 API key authentication
    - ⚡ Rate limiting
    - 📊 Usage tracking
    
    ## External API Access
    Use the `/api/v1/events` endpoints with an API key for programmatic access.
    """,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include external API router
app.include_router(events_router.router)

# Add CORS middleware
domain_name = os.getenv("DOMAIN_NAME")
logger.info(f"DOMAIN_NAME environment variable: '{domain_name}'")


if domain_name and domain_name not in ["your-domain.com", "localhost", ""]:
    # Production: Allow the actual domain and www subdomain
    allow_origins = [
        f"http://{domain_name}",
        f"https://{domain_name}",
        f"https://www.{domain_name}",
    ]
    logger.info(f"Production CORS configured for domain: {domain_name}")
else:
    # Development: Allow localhost and common dev ports
    allow_origins = [
        "http://localhost:3000", 
        "http://localhost:8000", 
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:8000", 
        "http://localhost:5173", 
        "http://127.0.0.1:5173"
    ]

# Always add Render frontend domain for deployment
render_frontend_domain = "https://locallifeassistant-frontend.onrender.com"
if render_frontend_domain not in allow_origins:
    allow_origins.append(render_frontend_domain)
    logger.info(f"Added Render frontend domain to CORS: {render_frontend_domain}")

# Log CORS configuration for debugging
logger.info(f"DOMAIN_NAME environment variable: '{domain_name}'")
logger.info(f"Allowed origins: {allow_origins}")

# Manual CORS middleware - simplified and more explicit
@app.middleware("http")
async def cors_middleware(request, call_next):
    origin = request.headers.get("origin")
    logger.info(f"CORS middleware - Origin: {origin}, Allowed origins: {allow_origins}")

    # Handle preflight requests
    if request.method == "OPTIONS":
        response = Response()
        # Set the origin header if it's in the allowed origins
        if origin in allow_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            logger.info(f"OPTIONS: Set Access-Control-Allow-Origin to {origin}")
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Max-Age"] = "600"
        # Add headers to help with Firebase Auth popups
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
        return response

    # Handle actual requests - ALWAYS call next first to get response
    response = await call_next(request)

    # Set CORS headers on the response
    if origin in allow_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        logger.info(f"GET/POST: Set Access-Control-Allow-Origin to {origin}")
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    # Add headers to help with Firebase Auth popups
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
    return response

# Add middleware to log CORS requests for debugging
@app.middleware("http")
async def log_cors_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    logger.info(f"CORS middleware - Origin: {origin}, Allowed origins: {allow_origins}")
    response = await call_next(request)
    return response

# Pydantic models
class ChatRequest(BaseModel):
    message: str
    conversation_history: List[Dict[str, Any]] = []
    llm_provider: str = "openai"
    user_preferences: Optional[UserPreferences] = None
    is_initial_response: bool = False  # Flag for welcome message response
    user_id: str  # NEW - Required anonymous user ID
    conversation_id: Optional[str] = None  # NEW

class ChatResponse(BaseModel):
    message: str
    recommendations: List[Dict[str, Any]] = []
    llm_provider_used: str
    cache_used: bool = False
    cache_age_hours: Optional[float] = None
    extracted_preferences: Optional[UserPreferences] = None  # NEW
    extraction_summary: Optional[str] = None  # NEW
    usage_stats: Optional[Dict[str, Any]] = None  # NEW - Trial info
    trial_exceeded: bool = False  # NEW - Flag to show registration prompt
    conversation_id: str  # NEW

class CreateConversationRequest(BaseModel):
    """Request model for creating a conversation"""
    user_id: str
    metadata: Optional[Dict[str, Any]] = None

# Cache configuration
CACHE_TTL_HOURS = 6  # Cache events for 6 hours

class MigrateConversationsRequest(BaseModel):
    """Request model for migrating conversations"""
    anonymous_user_id: str
    real_user_id: str

# Initialize services
event_crawler = EventCrawler()
cache_manager = CacheManager(ttl_hours=CACHE_TTL_HOURS)
search_service = SearchService()
extraction_service = ExtractionService()
usage_tracker = UsageTracker()
conversation_storage = ConversationStorage()
user_manager = UserManager()

# Conversations are now stored in Firestore
logger.info("Conversations storage: Firestore")

# Users are now stored in Firestore
logger.info("Users storage: Firestore")

# Routes
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "version": "2.1.0", 
        "features": ["smart_caching", "real_time_events", "city_based_cache"]
    }

@app.get("/stats")
async def get_stats():
    """Get system statistics including cache info"""
    try:
        cache_stats = cache_manager.get_cache_stats()
        
        return {
            "status": "active",
            "cache_stats": cache_stats,
            "features": ["smart_caching", "real_time_events", "city_based_cache", "llm_city_extraction"]
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/chat", response_model=ChatResponse)
async def smart_cached_chat(request: ChatRequest):
    """
    Smart cached chat endpoint
    Uses cache when available, fetches fresh data when needed
    """
    try:
        logger.info(f"Smart cached chat request: {request.message}")
        user_id = request.user_id

        # Check trial limit for anonymous users
        if user_id.startswith("user_"):  # Anonymous user
            if usage_tracker.check_trial_limit(user_id):
                # Trial exceeded - return prompt to register
                trial_limit = usage_tracker.trial_limit
                return ChatResponse(
                    message=f"🔒 You've reached your free trial limit of {trial_limit} interactions! Please register to continue using our service and keep your conversation history.",
                    recommendations=[],
                    llm_provider_used=request.llm_provider,
                    cache_used=False,
                    trial_exceeded=True,
                    usage_stats=usage_tracker.get_usage(user_id),
                    conversation_id="temp"
                )

        # Increment usage for anonymous users
        if user_id.startswith("user_"):
            usage_stats = usage_tracker.increment_usage(user_id)
        else:
            usage_stats = None

        # Get or create conversation
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = conversation_storage.create_conversation(user_id, {
                "llm_provider": request.llm_provider
            })

        # Save user message
        conversation_storage.save_message(user_id, conversation_id, {
            "role": "user",
            "content": request.message,
            "timestamp": datetime.now().isoformat()
        })
        
        # Step 1: Extract user preferences if this is an initial response
        extracted_preferences = None
        if request.is_initial_response:
            logger.info("Initial response detected, extracting user preferences")
            extracted_preferences = extraction_service.extract_user_preferences(request.message)
            logger.info(f"Extracted preferences: {extracted_preferences}")
        
        # Step 2: Determine city to use (prioritize extracted preferences)
        city = None
        location_provided = False
        
        # Priority 1: Use extracted location from preferences
        if extracted_preferences and extracted_preferences.location and extracted_preferences.location != "none":
            city = extracted_preferences.location.lower()
            location_provided = True
            logger.info(f"Using city from extracted preferences: {city}")
        
        # Priority 2: Try to extract city from query using existing method
        if not city:
            query_city = extraction_service.extract_location_from_query(request.message)
            if query_city:
                city = query_city.lower()
                location_provided = True
                logger.info(f"Using city from query extraction: {city}")
        
        
        # Step 3: Handle missing location for initial responses
        if request.is_initial_response and not location_provided:
            logger.info("No location provided in initial response, asking user for location")
            return ChatResponse(
                message="I'd be happy to help you find events! To give you the best recommendations, could you please tell me which city or area you're interested in? (e.g., 'New York', 'Los Angeles', 'Chicago', or a zipcode)",
                recommendations=[],
                llm_provider_used=request.llm_provider,
                cache_used=False,
                cache_age_hours=None,
                extracted_preferences=extracted_preferences,
                extraction_summary=None
            )
        
        # Step 4: Default fallback for non-initial responses or when location still missing
        if not city:
            city = "new york"
            logger.info("No city found, defaulting to New York")
            # If this is not an initial response and we're defaulting, inform the user
            if not request.is_initial_response:
                logger.info("Informing user that we're defaulting to New York")
        
        logger.info(f"Final city decision: {city}")
        # ------------------------------------------------------------
        
        # Step 5: Try to get cached events (will fetch fresh if expired)
        cached_events = cache_manager.get_cached_events(city, event_crawler)
        cache_age_hours = cache_manager.get_cache_age(city)

        if cached_events:
            logger.info(f"Using cached events for {city} (age: {cache_age_hours:.1f}h)")
            events = cached_events
            cache_used = cache_age_hours is not None and cache_age_hours > 0
        else:
            logger.warning(f"Failed to get any events for {city}")
            events = []
            cache_used = False
            cache_age_hours = None
        
        # Step 6: LLM-powered intelligent event search with preferences
        logger.info(f"Starting LLM search for query: '{request.message}' with {len(events)} events")
        
        # Convert UserPreferences object to dict for search service
        user_preferences_dict = None
        if extracted_preferences:
            user_preferences_dict = {
                'location': extracted_preferences.location,
                'date': extracted_preferences.date,
                'time': extracted_preferences.time,
                'event_type': extracted_preferences.event_type
            }
        
        top_events = await search_service.intelligent_event_search(
            request.message, 
            events, 
            user_preferences=user_preferences_dict
        )
        logger.info(f"LLM search returned {len(top_events)} events")
        
        # Debug: Check if events have LLM scores
        if top_events:
            first_event = top_events[0]
            logger.info(f"First event has llm_scores: {first_event.get('llm_scores', 'None')}")
            logger.info(f"First event relevance_score: {first_event.get('relevance_score', 'None')}")
        
        # Step 7: Format recommendations
        formatted_recommendations = []
        for event in top_events:
            formatted_recommendations.append({
                "type": "event",
                "data": {
                    **event,  # This includes llm_scores and relevance_score
                    "source": "cached" if cache_used else "realtime"
                },
                "relevance_score": event.get('relevance_score', 0.5),  # Keep for backward compatibility
                "explanation": f"Event in {city.title()}: {event.get('title', 'Unknown Event')}"
            })
        
        # Step 8: Generate response message
        location_note = ""
        if not location_provided and city == "new york":
            location_note = " (I couldn't determine your location, so I'm defaulting to New York)"
        
        if top_events:
            response_message = f"🎉 Found {len(top_events)} events in {city.title()} that match your search!{location_note} Check out the recommendations below ↓"
        else:
            response_message = f"😔 I couldn't find any events in {city.title()} matching your query.{location_note} Try asking about 'fashion events', 'music concerts', 'halloween parties', or 'free events'."
        
        # Step 9: Create extraction summary if preferences were extracted
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
        
        # Save assistant response
        conversation_storage.save_message(user_id, conversation_id, {
            "role": "assistant",
            "content": response_message,
            "timestamp": datetime.now().isoformat(),
            "recommendations": formatted_recommendations,
            "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
            "cache_used": cache_used,
            "cache_age_hours": cache_age_hours
        })

        # Update conversation metadata
        conversation_storage.update_metadata(user_id, conversation_id, {
            "last_message_at": datetime.now().isoformat()
        })
        
        return ChatResponse(
            message=response_message,
            recommendations=formatted_recommendations,
            llm_provider_used=request.llm_provider,
            cache_used=cache_used,
            cache_age_hours=cache_age_hours,
            extracted_preferences=extracted_preferences,
            extraction_summary=extraction_summary,
            usage_stats=usage_stats,
            trial_exceeded=False,
            conversation_id=conversation_id
        )
        
    except Exception as e:
        logger.error(f"Error in smart cached chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing chat request: {str(e)}")

async def stream_chat_response(request: ChatRequest):
    """Generator function for streaming chat responses"""
    try:
        logger.info(f"Streaming chat request: {request.message}")
        user_id = request.user_id
        
        # Check trial limit for anonymous users
        if user_id.startswith("user_"):  # Anonymous user
            if usage_tracker.check_trial_limit(user_id):
                # Trial exceeded - return prompt to register
                trial_limit = usage_tracker.trial_limit
                trial_message = f"🔒 You've reached your free trial limit of {trial_limit} interactions! Please register to continue using our service and keep your conversation history."
                yield f"data: {json.dumps({'type': 'message', 'content': trial_message, 'trial_exceeded': True})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
        
        # Increment usage for anonymous users
        if user_id.startswith("user_"):
            usage_stats = usage_tracker.increment_usage(user_id)
        else:
            usage_stats = None
        
        # Get or create conversation
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = conversation_storage.create_conversation(user_id, {
                "llm_provider": request.llm_provider
            })

        # Step 1: Extract user preferences first (so we can save them with message)
        extracted_preferences = None
        if request.is_initial_response:
            logger.info("Initial response detected, extracting user preferences")
            extracted_preferences = extraction_service.extract_user_preferences(request.message)
            logger.info(f"Extracted preferences: {extracted_preferences}")
        else:
            logger.info("Non-initial response detected")
        
        # Step 2: Determine city to use (prioritize extracted preferences)
        city = None
        location_provided = False
        
        # Priority 1: Use extracted location from preferences
        if extracted_preferences and extracted_preferences.location and extracted_preferences.location != "none":
            city = extracted_preferences.location.lower()
            location_provided = True
            logger.info(f"Using city from extracted preferences: {city}")
        
        # Priority 2: Try to extract city from query using existing method
        if not city:
            query_city = extraction_service.extract_location_from_query(request.message)
            if query_city:
                city = query_city.lower()
                location_provided = True
                # Update extracted_preferences with location if found via fallback
                if extracted_preferences:
                    extracted_preferences.location = query_city
                else:
                    from .extraction_service import UserPreferences
                    extracted_preferences = UserPreferences(location=query_city)
                logger.info(f"Using city from query extraction: {city}, updated extracted_preferences")
        
        # Save user message with extracted preferences (after we've determined location)
        # Only save for initial responses here - non-initial responses will be saved later
        if request.is_initial_response:
            prefs_dict = extracted_preferences.dict() if extracted_preferences else None
            logger.info(f"Saving initial user message with extracted_preferences: {prefs_dict}")
            conversation_storage.save_message(user_id, conversation_id, {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "extracted_preferences": prefs_dict
            })
            logger.info(f"Saved user message for conversation {conversation_id}, location in prefs: {prefs_dict.get('location') if prefs_dict else 'None'}")
        
        
        # Step 3: Handle missing location for initial responses
        if request.is_initial_response and not location_provided:
            logger.info("No location provided in initial response, asking user for location")
            location_message = "I'd be happy to help you find events! To give you the best recommendations, could you please tell me which city or area you're interested in? (e.g., 'New York', 'Los Angeles', 'Chicago', or a zipcode)"
            yield f"data: {json.dumps({'type': 'message', 'content': location_message})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        
        # Step 3.5: Check if location is provided but no event type (for initial responses)
        event_type_provided = extracted_preferences and extracted_preferences.event_type and extracted_preferences.event_type != "none"
        
        if request.is_initial_response and location_provided and not event_type_provided:
            logger.info("Location provided but no event type in initial response, asking for event type")
            follow_up_message = "Great! What kind of events are you interested in?"
            yield f"data: {json.dumps({'type': 'message', 'content': follow_up_message, 'location_processed': True, 'usage_stats': usage_stats, 'trial_exceeded': False, 'conversation_id': conversation_id})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
            # Save assistant message with stored location
            conversation_storage.save_message(user_id, conversation_id, {
                "role": "assistant",
                "content": follow_up_message,
                "timestamp": datetime.now().isoformat(),
                "recommendations": [],
                "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None
            })
            return
        
        # Step 3.6: For non-initial responses, retrieve location from conversation and extract event type
        if not request.is_initial_response:
            # Retrieve location from stored conversation
            stored_location = None
            try:
                logger.info(f"Retrieving conversation {conversation_id} for user {user_id} (anonymous: {user_id.startswith('user_')})")
                conversation = conversation_storage.get_conversation(user_id, conversation_id)
                if conversation:
                    logger.info(f"Conversation found, message count: {len(conversation.get('messages', []))}")
                    if conversation.get('messages'):
                        for idx, msg in enumerate(conversation.get('messages', [])):
                            if isinstance(msg, dict):
                                msg_role = msg.get('role')
                                msg_content = msg.get('content', '')[:50]
                                stored_prefs = msg.get('extracted_preferences')
                                logger.info(f"Message {idx}: role={msg_role}, content='{msg_content}...', has_prefs={stored_prefs is not None}")
                                if stored_prefs:
                                    if isinstance(stored_prefs, dict):
                                        location_value = stored_prefs.get('location')
                                        logger.info(f"  extracted_preferences dict: location={location_value}")
                                        if location_value and location_value != "none":
                                            stored_location = location_value
                                            logger.info(f"✓ Found stored location in message {idx}: {stored_location}")
                                            break
                                    else:
                                        logger.warning(f"  extracted_preferences is not a dict, type: {type(stored_prefs)}")
                else:
                    logger.warning(f"Conversation {conversation_id} not found or empty")
            except Exception as e:
                logger.error(f"Could not retrieve conversation to get stored location: {e}", exc_info=True)
            
            # Extract event type from current message
            if not extracted_preferences:
                extracted_preferences = extraction_service.extract_user_preferences(request.message)
            else:
                # If we already have preferences, try to extract event type from current message
                current_preferences = extraction_service.extract_user_preferences(request.message)
                if current_preferences:
                    if current_preferences.event_type and current_preferences.event_type != "none":
                        extracted_preferences.event_type = current_preferences.event_type
                    # Also check for other fields
                    if current_preferences.date and current_preferences.date != "none":
                        extracted_preferences.date = current_preferences.date
                    if current_preferences.time and current_preferences.time != "none":
                        extracted_preferences.time = current_preferences.time
            
            event_type_provided = extracted_preferences and extracted_preferences.event_type and extracted_preferences.event_type != "none"
            
            # Use stored location
            if stored_location:
                city = stored_location.lower()
                location_provided = True
                if extracted_preferences:
                    extracted_preferences.location = stored_location
                else:
                    from .extraction_service import UserPreferences
                    extracted_preferences = UserPreferences(location=stored_location)
                logger.info(f"Using stored location: {stored_location}")
            
            # Check if we have both location and event type
            if not location_provided:
                logger.warning("Non-initial response but no location found")
                location_message = "I need to know which city you're interested in. Could you please tell me the city or area?"
                yield f"data: {json.dumps({'type': 'message', 'content': location_message})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                # Save user message anyway
                conversation_storage.save_message(user_id, conversation_id, {
                    "role": "user",
                    "content": request.message,
                    "timestamp": datetime.now().isoformat(),
                    "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None
                })
                return
            
            if not event_type_provided:
                logger.warning("Non-initial response but no event type found")
                event_type_message = "What kind of events are you interested in?"
                yield f"data: {json.dumps({'type': 'message', 'content': event_type_message})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                # Save user message with stored location
                conversation_storage.save_message(user_id, conversation_id, {
                    "role": "user",
                    "content": request.message,
                    "timestamp": datetime.now().isoformat(),
                    "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None
                })
                return
            
            # Save user message with combined preferences (location + event type)
            conversation_storage.save_message(user_id, conversation_id, {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None
            })
        
        # Step 4: Default fallback for non-initial responses or when location still missing
        if not city:
            city = "new york"
            logger.info("No city found, defaulting to New York")
            # If this is not an initial response and we're defaulting, inform the user
            if not request.is_initial_response:
                logger.info("Informing user that we're defaulting to New York")
        
        logger.info(f"Final city decision: {city}, Event type: {extracted_preferences.event_type if extracted_preferences else 'none'}")
        
        # Step 5: Now proceed with event fetching (only when both location and event type are available)
        yield f"data: {json.dumps({'type': 'status', 'content': f'Searching for events in {city.title()}...'})}\n\n"
        await asyncio.sleep(0.3)

        # Get cached events (will fetch fresh automatically if expired)
        cached_events = cache_manager.get_cached_events(city, event_crawler)
        cache_age_hours = cache_manager.get_cache_age(city)

        if cached_events:
            events = cached_events
            if cache_age_hours is not None and cache_age_hours > 0:
                # Using cached events
                logger.info(f"Using cached events for {city} (age: {cache_age_hours:.1f}h)")
                cache_used = True
                yield f"data: {json.dumps({'type': 'status', 'content': f'Found cached events for {city.title()} (from {cache_age_hours:.1f}h ago)'})}\n\n"
            else:
                # Freshly fetched events
                logger.info(f"Fetched {len(events)} fresh events for {city}")
                cache_used = False
                yield f"data: {json.dumps({'type': 'status', 'content': f'Found {len(events)} fresh events for {city.title()}'})}\n\n"
        else:
            logger.warning(f"Failed to get any events for {city}")
            events = []
            cache_used = False
            cache_age_hours = None
        
        # Step 4: LLM-powered intelligent event search with preferences
        # Alternate between two similar messages to keep users engaged
        analysis_messages = [
            "Analyzing events with AI to find the best matches...",
            "Using AI to rank and filter the most relevant events..."
        ]
        
        logger.info(f"Starting LLM search for query: '{request.message}' with {len(events)} events")
        
        # Convert UserPreferences object to dict for search service
        user_preferences_dict = None
        if extracted_preferences:
            user_preferences_dict = {
                'location': extracted_preferences.location,
                'date': extracted_preferences.date,
                'time': extracted_preferences.time,
                'event_type': extracted_preferences.event_type
            }
        
        # Create a task for the AI processing
        async def ai_processing():
            return await search_service.intelligent_event_search(
                request.message, 
                events, 
                user_preferences=user_preferences_dict
            )
        
        # Start the AI processing task
        ai_task = asyncio.create_task(ai_processing())
        
        # Show alternating messages while AI is processing
        i = 0
        while not ai_task.done():
            message = analysis_messages[i % 2]  # Alternate between the two messages
            yield f"data: {json.dumps({'type': 'status', 'content': message})}\n\n"
            await asyncio.sleep(1.5)  # 1.5 second delay between messages
            logger.info(f"AI processing message: {message}")
            i += 1
        
        # Wait for AI processing to complete
        top_events = await ai_task
        logger.info(f"LLM search returned {len(top_events)} events")
        
        # Debug: Check if events have LLM scores
        if top_events:
            first_event = top_events[0]
            logger.info(f"First event has llm_scores: {first_event.get('llm_scores', 'None')}")
            logger.info(f"First event relevance_score: {first_event.get('relevance_score', 'None')}")
        
        # Step 5: Create extraction summary if preferences were extracted
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
        
        # Step 6: Generate and send main response message first
        location_note = ""
        if not location_provided and city == "new york":
            location_note = " (I couldn't determine your location, so I'm defaulting to New York)"
        
        if top_events:
            response_message = f"🎉 Found {len(top_events)} events in {city.title()} that match your search!{location_note} Check out the recommendations below ↓"
        else:
            response_message = f"😔 I couldn't find any events in {city.title()} matching your query.{location_note} Try asking about 'fashion events', 'music concerts', 'halloween parties', or 'free events'."
        
        # Determine if location was just processed (for follow-up message)
        location_just_processed = request.is_initial_response and location_provided
        
        # Send the main message first
        yield f"data: {json.dumps({'type': 'message', 'content': response_message, 'extraction_summary': extraction_summary, 'usage_stats': usage_stats, 'trial_exceeded': False, 'conversation_id': conversation_id, 'location_processed': location_just_processed})}\n\n"
        
        # Step 7: Format recommendations and stream them one by one
        yield f"data: {json.dumps({'type': 'status', 'content': f'Preparing {len(top_events)} recommendations...'})}\n\n"
        await asyncio.sleep(0.3)
        
        formatted_recommendations = []
        for i, event in enumerate(top_events):
            formatted_rec = {
                "type": "event",
                "data": {
                    **event,  # This includes llm_scores and relevance_score
                    "source": "cached" if cache_used else "realtime"
                },
                "relevance_score": event.get('relevance_score', 0.5),  # Keep for backward compatibility
                "explanation": f"Event in {city.title()}: {event.get('title', 'Unknown Event')}"
            }
            formatted_recommendations.append(formatted_rec)
            
            # Stream each recommendation
            yield f"data: {json.dumps({'type': 'recommendation', 'data': formatted_rec})}\n\n"
            await asyncio.sleep(0.2)  # Small delay between recommendations
        
        # Save assistant response
        conversation_storage.save_message(user_id, conversation_id, {
            "role": "assistant",
            "content": response_message,
            "timestamp": datetime.now().isoformat(),
            "recommendations": formatted_recommendations,
            "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
            "cache_used": cache_used,
            "cache_age_hours": cache_age_hours
        })

        # Update conversation metadata
        conversation_storage.update_metadata(user_id, conversation_id, {
            "last_message_at": datetime.now().isoformat()
        })
        
        # Signal completion
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        logger.error(f"Error in streaming chat: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'content': f'Error processing chat request: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

@app.post("/api/chat/stream")
async def stream_chat(request: ChatRequest):
    """
    Streaming chat endpoint using Server-Sent Events
    """
    return StreamingResponse(
        stream_chat_response(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        }
    )

@app.get("/api/usage/{user_id}")
async def get_user_usage(user_id: str):
    """Get usage statistics for a user"""
    usage = usage_tracker.get_usage(user_id)
    return usage


@app.post("/api/auth/register")
async def register_with_token(request: dict = Body(...)):
    """Register a Firebase-authenticated user and migrate their conversation history"""

    token = request.get("token")
    anonymous_user_id = request.get("anonymous_user_id")

    if not token:
        raise HTTPException(status_code=400, detail="Firebase token required")

    try:
        # Verify the Firebase token
        user_data = user_manager.authenticate_with_token(token)

        # The user is already created in Firebase Auth, now we just need to
        # migrate conversations and mark as registered
        real_user_id = user_data["user_id"]

        # Migrate conversations from anonymous to registered user
        migrated_count = conversation_storage.migrate_user_conversations(
            anonymous_user_id,
            real_user_id
        )

        # Mark as registered in usage tracker
        usage_tracker.mark_registered(anonymous_user_id, real_user_id)

        logger.info(f"User registered with Firebase: {user_data['email']} -> {real_user_id}")

        return {
            "success": True,
            "user_id": real_user_id,
            "migrated_conversations": migrated_count,
            "message": f"Registration successful! {migrated_count} conversations migrated."
        }
    except ValueError as e:
        logger.error(f"Firebase registration error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Firebase registration error (Unexpected): {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/api/auth/verify")
async def verify_auth_token(request: dict = Body(...)):
    """Verify Firebase Auth token"""

    token = request.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="No authentication token provided")

    try:
        user_data = user_manager.authenticate_with_token(token)
        return {
            "success": True,
            "user_id": user_data.get("user_id"),
            "email": user_data.get("email"),
            "name": user_data.get("name")
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/users/migrate-conversations")
async def migrate_conversations(request: MigrateConversationsRequest = Body(...)):
    """Migrate conversations from anonymous user to registered user"""
    # Now uses Firebase conversation storage
    try:
        migrated_count = conversation_storage.migrate_user_conversations(
            request.anonymous_user_id,
            request.real_user_id
        )

        return {
            "success": True,
            "migrated_conversations": migrated_count
        }
    except Exception as e:
        logger.error(f"Conversation migration failed: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/conversations/create")
async def create_conversation(request: CreateConversationRequest = Body(...)):
    """Create a new conversation for a user"""
    conversation_id = conversation_storage.create_conversation(request.user_id, request.metadata)
    return {"conversation_id": conversation_id}

@app.get("/api/conversations/{user_id}/{conversation_id}")
async def get_conversation(user_id: str, conversation_id: str):
    """Get specific conversation for a user"""
    try:
        conversation = conversation_storage.get_conversation(user_id, conversation_id)
        return conversation
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")

@app.get("/api/conversations/{user_id}/list")
async def list_user_conversations(user_id: str, limit: int = 50):
    """List all conversations for a specific user"""
    conversations = conversation_storage.list_user_conversations(user_id, limit)
    return {"conversations": conversations}

@app.delete("/api/conversations/{user_id}/{conversation_id}")
async def delete_conversation(user_id: str, conversation_id: str):
    """Delete a conversation"""
    try:
        conversation_storage.delete_conversation(user_id, conversation_id)
        return {"success": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")


@app.post("/api/cache/cleanup")
async def cleanup_cache():
    """Manually clean up expired cache files"""
    try:
        cache_manager.cleanup_old_cache()
        stats = cache_manager.get_cache_stats()
        return {
            "success": True,
            "message": "Cache cleanup completed",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error cleaning up cache: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get detailed cache statistics"""
    try:
        stats = cache_manager.get_cache_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    logger.info("Starting Smart Cached RAG Local Life Assistant...")
    logger.info("Features: City-based caching + Real-time events + Rate limit protection")
    logger.info(f"Cache TTL: {CACHE_TTL_HOURS} hours")
    
    # Clean up old cache on startup
    cache_manager.cleanup_old_cache()
    
    # Use PORT environment variable for Render deployment, fallback to 8000 for local development
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    
    uvicorn.run(app, host="0.0.0.0", port=port)