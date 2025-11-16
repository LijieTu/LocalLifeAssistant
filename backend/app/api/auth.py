#!/usr/bin/env python3
"""
API Key authentication and management for external API access.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from ..firebase_config import db


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class APIKey(BaseModel):
    """API Key model."""
    key_hash: str
    name: str
    created_at: datetime
    is_active: bool = True
    rate_limit_per_hour: int = 100


class APIKeyManager:
    """Manages API keys in Firebase."""
    
    COLLECTION = "api_keys"
    
    @staticmethod
    def hash_key(api_key: str) -> str:
        """Hash an API key for secure storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new API key."""
        return f"loco_{secrets.token_urlsafe(32)}"
    
    @classmethod
    def create_api_key(cls, name: str, rate_limit_per_hour: int = 100) -> str:
        """
        Create a new API key.
        
        Args:
            name: Descriptive name for the API key
            rate_limit_per_hour: Maximum requests per hour
            
        Returns:
            The generated API key (only shown once)
        """
        api_key = cls.generate_key()
        key_hash = cls.hash_key(api_key)
        
        key_data = APIKey(
            key_hash=key_hash,
            name=name,
            created_at=datetime.utcnow(),
            is_active=True,
            rate_limit_per_hour=rate_limit_per_hour,
        )
        
        db.collection(cls.COLLECTION).document(key_hash).set(key_data.model_dump())
        
        return api_key
    
    @classmethod
    def verify_key(cls, api_key: str) -> Optional[APIKey]:
        """
        Verify an API key and return its metadata.
        
        Args:
            api_key: The API key to verify
            
        Returns:
            APIKey object if valid, None otherwise
        """
        key_hash = cls.hash_key(api_key)
        doc = db.collection(cls.COLLECTION).document(key_hash).get()
        
        if not doc.exists:
            return None
        
        data = doc.to_dict()
        if not data.get("is_active", False):
            return None
        
        return APIKey(**data)
    
    @classmethod
    def revoke_key(cls, api_key: str) -> bool:
        """
        Revoke an API key.
        
        Args:
            api_key: The API key to revoke
            
        Returns:
            True if revoked, False if key not found
        """
        key_hash = cls.hash_key(api_key)
        doc_ref = db.collection(cls.COLLECTION).document(key_hash)
        
        if not doc_ref.get().exists:
            return False
        
        doc_ref.update({"is_active": False})
        return True


async def verify_api_key(api_key: str = Security(api_key_header)) -> APIKey:
    """
    Dependency to verify API key from request header.
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        APIKey object if valid
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include X-API-Key header.",
        )
    
    key_data = APIKeyManager.verify_key(api_key)
    
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
        )
    
    return key_data

