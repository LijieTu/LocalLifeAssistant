#!/usr/bin/env python3
"""
Rate limiting for API endpoints.
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from fastapi import HTTPException, Request, status

from ..firebase_config import db
from .auth import APIKey


class RateLimiter:
    """
    Rate limiter using Firebase for distributed rate limiting.
    Tracks requests per API key per hour.
    """
    
    COLLECTION = "rate_limits"
    
    @classmethod
    def _get_current_window(cls) -> str:
        """Get current hour window as string (YYYY-MM-DD-HH)."""
        return time.strftime("%Y-%m-%d-%H", time.gmtime())
    
    @classmethod
    def _get_doc_id(cls, key_hash: str) -> str:
        """Generate document ID for rate limit tracking."""
        window = cls._get_current_window()
        return f"{key_hash}_{window}"
    
    @classmethod
    def check_rate_limit(cls, api_key_data: APIKey) -> bool:
        """
        Check if request is within rate limit.
        
        Args:
            api_key_data: API key metadata with rate limit
            
        Returns:
            True if within limit, False if exceeded
        """
        doc_id = cls._get_doc_id(api_key_data.key_hash)
        doc_ref = db.collection(cls.COLLECTION).document(doc_id)
        
        doc = doc_ref.get()
        
        if not doc.exists:
            # First request in this window
            doc_ref.set({
                "key_hash": api_key_data.key_hash,
                "window": cls._get_current_window(),
                "count": 1,
                "limit": api_key_data.rate_limit_per_hour,
            })
            return True
        
        data = doc.to_dict()
        current_count = data.get("count", 0)
        
        if current_count >= api_key_data.rate_limit_per_hour:
            return False
        
        # Increment counter
        doc_ref.update({"count": current_count + 1})
        return True
    
    @classmethod
    def get_remaining_requests(cls, api_key_data: APIKey) -> Dict[str, int]:
        """
        Get remaining requests for the current window.
        
        Args:
            api_key_data: API key metadata
            
        Returns:
            Dict with 'remaining' and 'limit' counts
        """
        doc_id = cls._get_doc_id(api_key_data.key_hash)
        doc = db.collection(cls.COLLECTION).document(doc_id).get()
        
        if not doc.exists:
            return {
                "remaining": api_key_data.rate_limit_per_hour,
                "limit": api_key_data.rate_limit_per_hour,
            }
        
        data = doc.to_dict()
        current_count = data.get("count", 0)
        
        return {
            "remaining": max(0, api_key_data.rate_limit_per_hour - current_count),
            "limit": api_key_data.rate_limit_per_hour,
        }


async def check_rate_limit(request: Request, api_key_data: APIKey) -> None:
    """
    Dependency to check rate limit before processing request.
    
    Args:
        request: FastAPI request object
        api_key_data: Verified API key data
        
    Raises:
        HTTPException: If rate limit exceeded
    """
    if not RateLimiter.check_rate_limit(api_key_data):
        remaining = RateLimiter.get_remaining_requests(api_key_data)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Limit: {remaining['limit']} requests/hour. Try again in the next hour.",
            headers={
                "X-RateLimit-Limit": str(remaining["limit"]),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "3600",
            },
        )
    
    # Add rate limit info to response headers
    remaining = RateLimiter.get_remaining_requests(api_key_data)
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(remaining["limit"]),
        "X-RateLimit-Remaining": str(remaining["remaining"]),
    }

