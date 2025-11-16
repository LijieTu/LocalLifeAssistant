#!/usr/bin/env python3
"""
Public API endpoints for event fetching.
External developers can use these endpoints with API keys.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...core.container import get_service_container
from ..auth import APIKey, verify_api_key
from ..rate_limiter import check_rate_limit, RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["Events API"])


class EventSearchRequest(BaseModel):
    """Request model for event search."""
    city: str = Field(..., description="City name (e.g., 'San Francisco', 'New York')")
    max_pages: int = Field(default=3, ge=1, le=10, description="Maximum pages to fetch (1-10)")
    max_results: Optional[int] = Field(default=None, ge=1, le=100, description="Maximum number of results (1-100)")
    providers: Optional[List[str]] = Field(default=None, description="Specific providers to use (e.g., ['eventbrite'])")


class EventSearchResponse(BaseModel):
    """Response model for event search."""
    success: bool
    city: str
    total_events: int
    events: List[Dict[str, Any]]
    providers_used: List[str]


class APIKeyInfo(BaseModel):
    """API key information response."""
    name: str
    rate_limit_per_hour: int
    requests_remaining: int


@router.post(
    "/search",
    response_model=EventSearchResponse,
    summary="Search events by city",
    description="""
    Search for events in a specific city using various event providers.
    
    **Authentication**: Requires `X-API-Key` header.
    
    **Rate Limit**: 100 requests per hour (default, may vary by API key).
    
    **Supported Cities**: San Francisco, New York, Los Angeles, Miami, Chicago, Seattle, Boston.
    
    **Example Request**:
    ```json
    {
        "city": "San Francisco",
        "max_pages": 3,
        "max_results": 50,
        "providers": ["eventbrite"]
    }
    ```
    """,
)
async def search_events(
    request: Request,
    search_request: EventSearchRequest,
    api_key_data: APIKey = Depends(verify_api_key),
) -> EventSearchResponse:
    """
    Search for events in a specific city.
    
    Args:
        request: FastAPI request object
        search_request: Search parameters
        api_key_data: Verified API key data
        
    Returns:
        EventSearchResponse with list of events
        
    Raises:
        HTTPException: If search fails or rate limit exceeded
    """
    # Check rate limit
    await check_rate_limit(request, api_key_data)
    
    try:
        container = get_service_container()
        aggregator = container.event_aggregator
        
        logger.info(
            "API event search: city=%s, max_pages=%d, max_results=%s, providers=%s, api_key=%s",
            search_request.city,
            search_request.max_pages,
            search_request.max_results,
            search_request.providers,
            api_key_data.name,
        )
        
        events = aggregator.fetch_by_city(
            search_request.city,
            provider_names=search_request.providers,
            max_pages=search_request.max_pages,
            max_results=search_request.max_results,
        )
        
        # Determine which providers were used
        providers_used = search_request.providers or [p.name for p in aggregator.providers]
        
        response = EventSearchResponse(
            success=True,
            city=search_request.city,
            total_events=len(events),
            events=events,
            providers_used=providers_used,
        )
        
        return response
        
    except Exception as e:
        logger.error("Event search failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Event search failed: {str(e)}",
        )


@router.get(
    "/providers",
    summary="List available event providers",
    description="Get a list of all available event providers and their supported cities.",
)
async def list_providers(
    api_key_data: APIKey = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    List all available event providers.
    
    Args:
        api_key_data: Verified API key data
        
    Returns:
        Dict with provider information
    """
    container = get_service_container()
    aggregator = container.event_aggregator
    
    providers_info = []
    for provider in aggregator.providers:
        providers_info.append({
            "name": provider.name,
            "supported_cities": [
                "San Francisco",
                "New York",
                "Los Angeles",
                "Miami",
                "Chicago",
                "Seattle",
                "Boston",
            ],
        })
    
    return {
        "success": True,
        "providers": providers_info,
    }


@router.get(
    "/key-info",
    response_model=APIKeyInfo,
    summary="Get API key information",
    description="Get information about your API key including rate limits and remaining requests.",
)
async def get_key_info(
    request: Request,
    api_key_data: APIKey = Depends(verify_api_key),
) -> APIKeyInfo:
    """
    Get information about the current API key.
    
    Args:
        request: FastAPI request object
        api_key_data: Verified API key data
        
    Returns:
        APIKeyInfo with key details
    """
    from ..rate_limiter import RateLimiter
    
    remaining = RateLimiter.get_remaining_requests(api_key_data)
    
    return APIKeyInfo(
        name=api_key_data.name,
        rate_limit_per_hour=api_key_data.rate_limit_per_hour,
        requests_remaining=remaining["remaining"],
    )

