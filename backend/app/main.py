#!/usr/bin/env python3
"""
Smart Cached RAG Local Life Assistant
Combines real-time fetching with intelligent city-based caching
"""

import logging
import os
from typing import Dict, Any, List, Optional, Tuple
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
from .extraction_service import UserPreferences
from .usage_tracker import UsageTracker
from .conversation_storage import ConversationStorage
from .user_manager import UserManager
from .background_fetcher import BackgroundEventFetcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Load environment variables from .env file
load_dotenv('../.env') or load_dotenv('.env') or load_dotenv('/app/.env')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Smart Cached RAG Local Life Assistant", version="2.1.0")

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

# # Always add Render frontend domain for deployment
# render_frontend_domain = "https://locallifeassistant-frontend.onrender.com"
# if render_frontend_domain not in allow_origins:
#     allow_origins.append(render_frontend_domain)
#     logger.info(f"Added Render frontend domain to CORS: {render_frontend_domain}")

# # Log CORS configuration for debugging
# logger.info(f"DOMAIN_NAME environment variable: '{domain_name}'")

# Manual CORS middleware - simplified and more explicit
@app.middleware("http")
async def cors_middleware(request, call_next):
    origin = request.headers.get("origin")
    # logger.info(f"CORS middleware - Origin: {origin}, Allowed origins: {allow_origins}")

    # Handle preflight requests
    if request.method == "OPTIONS":
        response = Response()
        # Set the origin header if it's in the allowed origins
        if origin in allow_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            # logger.info(f"OPTIONS: Set Access-Control-Allow-Origin to {origin}")
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
        # logger.info(f"GET/POST: Set Access-Control-Allow-Origin to {origin}")
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
    # logger.info(f"CORS middleware - Origin: {origin}, Allowed origins: {allow_origins}")
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
CACHE_TTL_HOURS = 8  # Cache events for 8 hours (2x refresh interval for buffer)

class MigrateConversationsRequest(BaseModel):
    """Request model for migrating conversations"""
    anonymous_user_id: str
    real_user_id: str

# Initialize services
event_crawler = EventCrawler()
cache_manager = CacheManager(ttl_hours=CACHE_TTL_HOURS)
search_service = SearchService()
usage_tracker = UsageTracker()
conversation_storage = ConversationStorage()
user_manager = UserManager()
background_fetcher = BackgroundEventFetcher(cache_manager, event_crawler)

# Initialize background scheduler
scheduler = AsyncIOScheduler()

# Conversations are now stored in Firestore
logger.info("Conversations storage: Firestore")

# Users are now stored in Firestore
logger.info("Users storage: Firestore")


# Helper function to format city name
def format_city_name(city: str) -> str:
    """Format city name from snake_case to Title Case"""
    return city.replace('_', ' ').title()

def normalize_city_name(city: str) -> str:
    """Convert Title Case city name to snake_case for backend processing"""
    return city.lower().replace(' ', '_')

# Background scheduler setup
@app.on_event("startup")
async def startup_event():
    """Initialize background scheduler on app startup"""
    try:
        # Schedule background event fetch job to run every 4 hours
        # AsyncIOScheduler can handle sync functions by running them in executor
        scheduler.add_job(
            background_fetcher.fetch_all_events,
            trigger=CronTrigger(hour='*/4', minute=0),  # Every 4 hours at minute 0
            id='background_event_fetch',
            name='Background Event Fetch',
            replace_existing=True,
            executor='default'  # Runs sync function in thread pool
        )
        scheduler.start()
        logger.info("Background scheduler started - event fetch job scheduled every 4 hours")
        
        # Run initial fetch on startup in background (non-blocking)
        # This ensures cache is populated immediately on startup
        logger.info("Running initial background event fetch on startup...")
        def run_fetch():
            try:
                background_fetcher.fetch_all_events()
            except Exception as e:
                logger.error(f"Error in initial background fetch: {e}", exc_info=True)
        asyncio.create_task(asyncio.to_thread(run_fetch))
    except Exception as e:
        logger.error(f"Error starting background scheduler: {e}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown background scheduler gracefully"""
    try:
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("Background scheduler shut down gracefully")
    except Exception as e:
        logger.error(f"Error shutting down background scheduler: {e}", exc_info=True)

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

@app.get("/api/supported-event-types")
async def get_supported_event_types():
    """Get list of supported event types for frontend buttons"""
    try:
        supported_types = event_crawler.get_supported_events()
        return {
            "success": True,
            "event_types": supported_types
        }
    except Exception as e:
        logger.error(f"Error getting supported event types: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/supported-cities")
async def get_supported_cities():
    """Get list of supported cities for frontend buttons"""
    try:
        supported_cities = event_crawler.get_supported_cities()
        return {
            "success": True,
            "cities": supported_cities
        }
    except Exception as e:
        logger.error(f"Error getting supported cities: {e}")
        return {"success": False, "error": str(e)}


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
                trial_message = (
                    f"🔒 You've reached your free trial limit of {trial_limit} interactions! "
                    f"Please register to continue using our service and keep your conversation history."
                )
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

        # Step 1: Extract city and event type from message format "city:event_type: message" or "city: message"
        city = None
        location_provided = False
        extracted_preferences = None
        
        message_lower = request.message.lower().strip()
        supported_cities = event_crawler.get_supported_cities()
        supported_event_types = event_crawler.get_supported_events()
        
        logger.info(f"Received message: '{request.message}'")
        logger.info(f"Supported cities (first 5): {supported_cities[:5] if len(supported_cities) > 5 else supported_cities}")
        logger.info(f"Supported event types: {supported_event_types}")
        
        # Extract city and event type from message format "city:event_type: message" or "city: message"
        # Frontend always sends this format, so message_parts is guaranteed to have at least 2 parts
        message_parts = request.message.split(':', 2)
        logger.info(f"Message parts after split: {message_parts}, length: {len(message_parts)}")
        
        # First part is always the city (in snake_case from frontend)
        potential_city = message_parts[0].strip().lower()
        logger.info(f"Potential city from message: '{potential_city}'")
        
        # Check if the city is in supported cities (already in snake_case from frontend)
        if potential_city in supported_cities:
            city = potential_city
            location_provided = True
            logger.info(f"City '{city}' found in supported_cities")
        else:
            # Try normalizing the city name (in case frontend sends Title Case)
            normalized_city = normalize_city_name(message_parts[0].strip())
            if normalized_city in supported_cities:
                city = normalized_city
                location_provided = True
                logger.info(f"City '{normalized_city}' found after normalization")
            else:
                logger.warning(f"City '{potential_city}' not found in supported_cities, defaulting to New York")
                city = "new york"
                location_provided = False
        
        # Check for event type (format: "city:event_type: message" or "city: message")
        if len(message_parts) >= 3:
            # Format: "city:event_type: message"
            potential_event_type = message_parts[1].strip().lower()
            actual_message = message_parts[2].strip().lower()
            logger.info(f"Checking potential event type '{potential_event_type}' in supported_event_types")
            
            # First, check if message text contains a valid event type (user's manual input takes priority)
            # Extract words from message and check for event type keywords
            message_event_type = None
            message_words = actual_message.split()
            
            # Check for exact word match first (e.g., "find music" -> "music")
            for event_type in supported_event_types:
                if event_type in message_words:
                    message_event_type = event_type
                    logger.info(f"Found valid event type '{event_type}' as word in message text")
                    break
            
            # If no exact word match, check substring (e.g., "findmusic" -> "music")
            if not message_event_type:
                for event_type in supported_event_types:
                    if event_type in actual_message:
                        message_event_type = event_type
                        logger.info(f"Found valid event type '{event_type}' as substring in message text")
                        break
            
            # If message text has a valid event type, use it (user's manual input overrides prefix)
            if message_event_type:
                extracted_preferences = UserPreferences(location=city, event_type=message_event_type)
                logger.info(f"✓ Using event type '{message_event_type}' from message text (overriding prefix '{potential_event_type}')")
            elif potential_event_type in supported_event_types:
                # No valid event type in message text, use prefix
                extracted_preferences = UserPreferences(location=city, event_type=potential_event_type)
                logger.info(f"✓ Extracted city '{city}' and event type '{potential_event_type}' from message prefix")
            else:
                logger.warning(f"Event type '{potential_event_type}' not found in supported_event_types and no valid event type in message")
                extracted_preferences = UserPreferences(location=city)
                logger.info(f"Extracted city '{city}' from message, no event type found")
        elif len(message_parts) == 2:
            # Format: "city: message" - check message for event type
            actual_message = message_parts[1].strip().lower()
            message_words = actual_message.split()
            
            # Check for exact word match first
            for event_type in supported_event_types:
                if event_type in message_words:
                    extracted_preferences = UserPreferences(location=city, event_type=event_type)
                    logger.info(f"Extracted city '{city}' and event type '{event_type}' from message content (word match)")
                    break
            
            # If no exact word match, check substring
            if not extracted_preferences:
                for event_type in supported_event_types:
                    if event_type in actual_message:
                        extracted_preferences = UserPreferences(location=city, event_type=event_type)
                        logger.info(f"Extracted city '{city}' and event type '{event_type}' from message content (substring match)")
                        break
            
            if not extracted_preferences:
                extracted_preferences = UserPreferences(location=city)
                logger.info(f"Extracted city '{city}' from message, no event type found")
        else:
            # Format: single part message (no colons) - could be city, event type, or regular query
            single_message = message_parts[0].strip().lower()
            logger.info(f"Single-part message detected: '{single_message}'")
            single_message_words = single_message.split()
            
            # First, try to extract city from the message (keyword extraction)
            extracted_city = None
            if not city or not location_provided:
                # Check for exact match
                if single_message in supported_cities:
                    extracted_city = single_message
                    logger.info(f"Extracted city '{extracted_city}' from single-part message (exact match)")
                else:
                    # Try keyword extraction - check if any city name appears as words in the message
                    for supported_city in supported_cities:
                        city_words = supported_city.split('_')  # Cities are in snake_case
                        # Check if all words of city name appear in message
                        if all(word in single_message_words for word in city_words):
                            extracted_city = supported_city
                            logger.info(f"Extracted city '{extracted_city}' from single-part message (keyword match)")
                            break
                    # Also check normalized version
                    if not extracted_city:
                        normalized_single = normalize_city_name(single_message)
                        if normalized_single in supported_cities:
                            extracted_city = normalized_single
                            logger.info(f"Extracted city '{extracted_city}' from single-part message (normalized match)")
            
            # Use extracted city if found, otherwise use the one from prefix (if any)
            final_city = extracted_city if extracted_city else city
            
            # Check if it's an event type (exact match)
            if single_message in supported_event_types:
                extracted_preferences = UserPreferences(
                    location=final_city if final_city else None,
                    event_type=single_message
                )
                logger.info(f"Extracted event type '{single_message}' from single-part message (exact match)")
            # Check if message contains event type (keyword extraction)
            elif final_city or city:
                # City was extracted or provided, check if message contains event type
                # Check for exact word match first
                for event_type in supported_event_types:
                    if event_type in single_message_words:
                        extracted_preferences = UserPreferences(location=final_city or city, event_type=event_type)
                        logger.info(f"Extracted city '{final_city or city}' and event type '{event_type}' from single-part message (word match)")
                        break
                
                # If no exact word match, check substring
                if not extracted_preferences:
                    for event_type in supported_event_types:
                        if event_type in single_message:
                            extracted_preferences = UserPreferences(location=final_city or city, event_type=event_type)
                            logger.info(f"Extracted city '{final_city or city}' and event type '{event_type}' from single-part message (substring match)")
                            break
                
                if not extracted_preferences:
                    extracted_preferences = UserPreferences(location=final_city or city)
                    logger.info(f"Extracted city '{final_city or city}' from single-part message, no event type found")
            else:
                # Neither city nor event type - treat as regular query
                extracted_preferences = UserPreferences(location=city) if city else None
                logger.info(f"Single-part message treated as regular query, city: {city}")

        # Save user message with extracted preferences (after we've determined location)
        # Only save for initial responses here - non-initial responses will be saved later
        if request.is_initial_response:
            prefs_dict = extracted_preferences.dict() if extracted_preferences else None
            logger.info(f"Saving initial user message with extracted_preferences: {prefs_dict}")
            # Save in background (non-blocking)
            asyncio.create_task(conversation_storage.save_message_async(user_id, conversation_id, {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "extracted_preferences": prefs_dict
            }))
            logger.info(f"Queued user message save for conversation {conversation_id}, location in prefs: {prefs_dict.get('location') if prefs_dict else 'None'}")
        
        
        # Step 3: Save user message for non-initial responses
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
            
            # Check if message is a supported event type (from button selection)
            supported_event_types = event_crawler.get_supported_events()
            message_lower = request.message.lower().strip()
            if message_lower in supported_event_types:
                # User selected event type from button
                if extracted_preferences:
                    extracted_preferences.event_type = message_lower
                else:
                    extracted_preferences = UserPreferences(event_type=message_lower)
                logger.info(f"Using event type from button selection: {message_lower}")
            
            # Use stored location if available
            if stored_location and not location_provided:
                city = stored_location.lower()
                location_provided = True
                if extracted_preferences:
                    extracted_preferences.location = stored_location
                else:
                    extracted_preferences = UserPreferences(location=stored_location)
                logger.info(f"Using stored location: {stored_location}")
            
            # Save user message with combined preferences (location + event type)
            # Save in background (non-blocking)
            asyncio.create_task(conversation_storage.save_message_async(user_id, conversation_id, {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None
            }))
        
        logger.info(f"Final city decision: {city}, Event type: {extracted_preferences.event_type if extracted_preferences else 'none'}")
        
        # Step 3: Pre-cache all event types for this city (if not already cached)
        # This allows frontend to show event type buttons and retrieve instantly
        cache_manager.cache_all_event_types_for_city(city, event_crawler)
        
        # Determine event type/category for current request
        event_type = "events"  # default
        if extracted_preferences and extracted_preferences.event_type and extracted_preferences.event_type != "none":
            event_type = extracted_preferences.event_type.lower()
            logger.info(f"Using extracted event type: {event_type}")
        else:
            logger.warning(f"No event type extracted, using default 'events'. Extracted preferences: {extracted_preferences.dict() if extracted_preferences else None}")
        
        # Step 6: Get cached events for the selected event type (should be instant now)
        # Get cached events - will use cache if available, or fetch fresh if cache is missing
        # Pass event_crawler as fallback to fetch fresh events if cache is completely missing
        cached_events = cache_manager.get_cached_events(city, event_type=event_type, event_crawler=event_crawler)
        cache_age_hours = cache_manager.get_cache_age(city, event_type=event_type)

        if cached_events:
            events = cached_events
            if cache_age_hours is not None and cache_age_hours > 0:
                # Using cached events
                logger.info(f"Using cached events for {city} (age: {cache_age_hours:.1f}h)")
                cache_used = True
            else:
                # Freshly fetched events (cache was missing, so we fetched synchronously)
                logger.info(f"Fetched {len(events)} fresh events for {city} (cache was missing)")
                cache_used = False
        else:
            logger.warning(f"Failed to get any events for {city}/{event_type}")
            events = []
            cache_used = False
            cache_age_hours = None
        
        # Step 4: LLM-powered intelligent event search with preferences
        # Alternate between two similar messages to keep users engaged
        analysis_messages = [
            "Analyzing events with AI to find the best matches...",
            "Using AI to rank and filter the most relevant events..."
        ]
        
        # Extract the actual user query (remove city:event_type: prefix if present)
        actual_user_query = request.message
        if ':' in request.message:
            # Check if message has format "city:event_type: message" or "city: message"
            message_parts = request.message.split(':', 2)
            if len(message_parts) >= 2:
                # Check if first part is a city
                potential_city = message_parts[0].strip().lower()
                if potential_city in supported_cities:
                    # This is a prefixed message, extract the actual user input
                    if len(message_parts) == 3:
                        # Format: "city:event_type: message"
                        actual_user_query = message_parts[2].strip()
                    elif len(message_parts) == 2:
                        # Format: "city: message"
                        actual_user_query = message_parts[1].strip()
                    logger.info(f"Extracted actual user query: '{actual_user_query}' from prefixed message: '{request.message}'")
        
        # Check if we need LLM processing
        # Skip LLM if user just selected city/event type without a query (empty or just event type)
        needs_llm_processing = bool(actual_user_query and actual_user_query.strip() and 
                                    actual_user_query.strip().lower() not in supported_event_types)
        
        if not needs_llm_processing:
            # No actual query - just return top events for the selected city/event type
            # This is much faster (no LLM call needed) for initial city/event type selection
            logger.info(f"Skipping LLM processing - no actual query provided, returning top events for {city}/{event_type}")
            
            # Rank events by quality and relevance (simple heuristic-based ranking)
            def rank_event(event):
                """Simple ranking function for events when LLM is not used"""
                score = 0
                
                # Prioritize events happening soon (within next 7 days get bonus)
                start_datetime_str = event.get('start_datetime', '')
                if start_datetime_str:
                    try:
                        from datetime import datetime
                        if 'T' in start_datetime_str:
                            event_time = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
                        else:
                            event_time = datetime.fromisoformat(start_datetime_str)
                        
                        days_until = (event_time - datetime.now()).days
                        if 0 <= days_until <= 7:
                            score += 10  # Events happening soon
                        elif days_until < 0:
                            score -= 100  # Past events (should be filtered, but just in case)
                        else:
                            score += max(0, 10 - days_until // 7)  # Further events get lower score
                    except:
                        pass
                
                # Free events get bonus
                if event.get('is_free', False):
                    score += 5
                
                # Events with images are more complete/higher quality
                if event.get('image_url'):
                    score += 3
                
                # Events with descriptions are more complete
                if event.get('description') and len(event.get('description', '')) > 50:
                    score += 2
                
                # Events with venue information are more complete
                if event.get('venue_name'):
                    score += 2
                
                # Prefer certain sources (more reliable)
                source = event.get('source', '').lower()
                if source in ['eventbrite', 'ticketmaster']:
                    score += 2
                elif source in ['meetup', 'predicthq']:
                    score += 1
                
                return score
            
            # Sort events by rank (highest score first)
            ranked_events = sorted(events, key=rank_event, reverse=True)
            top_events = ranked_events[:10]  # Return top 10 ranked events
            
            # Add relevance scores for consistency with LLM results
            for i, event in enumerate(top_events):
                event['relevance_score'] = 10 - i  # Simple ranking (10, 9, 8, ...)
            
            logger.info(f"Ranked and selected top {len(top_events)} events from {len(events)} total events")
        else:
            # User provided an actual query - use LLM to intelligently rank events
            logger.info(f"Starting LLM search for actual user query: '{actual_user_query}' (original message: '{request.message}') with {len(events)} events")
            
            # Convert UserPreferences object to dict for search service
            user_preferences_dict = None
            if extracted_preferences:
                user_preferences_dict = {
                    'location': extracted_preferences.location,
                    'date': extracted_preferences.date,
                    'time': extracted_preferences.time,
                    'event_type': extracted_preferences.event_type
                }
                logger.info(f"User preferences being used: {user_preferences_dict}")
            else:
                logger.warning("No user preferences extracted - extracted_preferences is None or empty")
            
            # Create a task for the AI processing
            async def ai_processing():
                return await search_service.intelligent_event_search(
                    actual_user_query,  # Use the actual user query, not the prefixed message
                    events, 
                    user_preferences=user_preferences_dict
                )
            
            # Start the AI processing task
            ai_task = asyncio.create_task(ai_processing())
            
            # Send first status message immediately to ensure it's shown
            yield f"data: {json.dumps({'type': 'status', 'content': analysis_messages[0]})}\n\n"
            logger.info(f"AI processing message: {analysis_messages[0]}")
            await asyncio.sleep(0.5)  # Small delay to ensure message is sent
            
            # Show alternating messages while AI is processing
            i = 1
            while not ai_task.done():
                message = analysis_messages[i % 2]  # Alternate between the two messages
                yield f"data: {json.dumps({'type': 'status', 'content': message})}\n\n"
                logger.info(f"AI processing message: {message}")
                await asyncio.sleep(1.5)  # 1.5 second delay between messages
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
        # if extracted_preferences:
        #     summary_parts = []
        #     if extracted_preferences.location and extracted_preferences.location != "none":
        #         summary_parts.append(f"📍 {extracted_preferences.location}")
        #     if extracted_preferences.date and extracted_preferences.date != "none":
        #         summary_parts.append(f"📅 {extracted_preferences.date}")
        #     if extracted_preferences.time and extracted_preferences.time != "none":
        #         summary_parts.append(f"🕐 {extracted_preferences.time}")
        #     if extracted_preferences.event_type and extracted_preferences.event_type != "none":
        #         summary_parts.append(f"🎭 {extracted_preferences.event_type}")
        #     
        #     if summary_parts:
        #         extraction_summary = " • ".join(summary_parts)
        
        # Step 6: Generate and send main response message first
        location_note = ""
        if not location_provided and city == "new york":
            location_note = " (I couldn't determine your location, so I'm defaulting to New York)"
        
        # Format event type for display (only if not default "events")
        event_type_display = ""
        if event_type and event_type != "events":
            event_type_display = f'"{event_type}" '
        
        if top_events:
            response_message = (
                f"Found {len(top_events)} {event_type_display} events in {format_city_name(city)} that match your search!"
                f"{location_note} Check out the recommendations ↓"
            )
        else:
            response_message = (
                f"😔 I couldn't find any {event_type_display} events in {format_city_name(city)} matching your query."
                f"{location_note} Try asking about 'fashion events', 'music concerts', "
                f"'halloween parties', or 'free events'."
            )
        
        # Determine if location was just processed (for follow-up message)
        location_just_processed = request.is_initial_response and location_provided
        
        # Send the main message first
        yield f"data: {json.dumps({'type': 'message', 'content': response_message, 'extraction_summary': extraction_summary, 'usage_stats': usage_stats, 'trial_exceeded': False, 'conversation_id': conversation_id, 'location_processed': location_just_processed})}\n\n"
        
        # # Longer delay to ensure message is fully rendered before recommendations start
        # # This prevents the message from appearing after recommendations
        # await asyncio.sleep(0.8)
        
        # Step 7: Format recommendations and stream them one by one
        formatted_recommendations = []
        logger.info(f"📤 Starting to stream {len(top_events)} recommendations")
        for i, event in enumerate(top_events):
            formatted_rec = {
                "type": "event",
                "data": {
                    **event,  # This includes llm_scores and relevance_score
                    "source": "cached" if cache_used else "realtime"
                },
                "relevance_score": event.get('relevance_score', 0.5),  # Keep for backward compatibility
                "explanation": f"Event in {format_city_name(city)}: {event.get('title', 'Unknown Event')}"
            }
            formatted_recommendations.append(formatted_rec)
            
            # Stream each recommendation
            event_title = event.get('title', 'Unknown Event')
            logger.info(f"📤 Streaming recommendation {i+1}/{len(top_events)}: {event_title}")
            yield f"data: {json.dumps({'type': 'recommendation', 'data': formatted_rec})}\n\n"
            await asyncio.sleep(0.2)  # Small delay between recommendations
        
        # Save assistant response (in background, non-blocking)
        asyncio.create_task(conversation_storage.save_message_async(user_id, conversation_id, {
            "role": "assistant",
            "content": response_message,
            "timestamp": datetime.now().isoformat(),
            "recommendations": formatted_recommendations,
            "extracted_preferences": extracted_preferences.dict() if extracted_preferences else None,
            "cache_used": cache_used,
            "cache_age_hours": cache_age_hours
        }))

        # Update conversation metadata (in background, non-blocking)
        asyncio.create_task(conversation_storage.update_metadata_async(user_id, conversation_id, {
            "last_message_at": datetime.now().isoformat()
        }))
        
        # Ensure all recommendations are sent before signaling completion
        logger.info(f"✅ All {len(formatted_recommendations)} recommendations sent, signaling completion")
        
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
            "message": (
                f"Registration successful! {migrated_count} conversations migrated."
            )
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


@app.get("/api/background/status")
async def get_background_status():
    """Get background job status and last refresh time"""
    try:
        last_refresh = background_fetcher.get_last_refresh_time()
        scheduler_status = {
            'running': scheduler.running,
            'jobs': []
        }
        
        if scheduler.running:
            for job in scheduler.get_jobs():
                scheduler_status['jobs'].append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
                })
        
        return {
            'success': True,
            'scheduler': scheduler_status,
            'last_refresh': last_refresh,
            'cache_ttl_hours': CACHE_TTL_HOURS
        }
    except Exception as e:
        logger.error(f"Error getting background status: {e}")
        return {
            'success': False,
            'error': str(e)
        }

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