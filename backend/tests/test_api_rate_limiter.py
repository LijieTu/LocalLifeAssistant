#!/usr/bin/env python3
"""
Tests for API rate limiting.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime


class FakeFirestore:
    """Fake Firestore for testing."""
    
    def __init__(self):
        self.data = {}
    
    def collection(self, name):
        if name not in self.data:
            self.data[name] = {}
        return FakeCollection(self.data[name])


class FakeCollection:
    """Fake Firestore collection."""
    
    def __init__(self, data):
        self.data = data
    
    def document(self, doc_id):
        return FakeDocument(self.data, doc_id)


class FakeDocument:
    """Fake Firestore document."""
    
    def __init__(self, data, doc_id):
        self.data = data
        self.doc_id = doc_id
    
    def set(self, value):
        self.data[self.doc_id] = value
    
    def get(self):
        return FakeDocSnapshot(self.data.get(self.doc_id))
    
    def update(self, updates):
        if self.doc_id in self.data:
            self.data[self.doc_id].update(updates)


class FakeDocSnapshot:
    """Fake Firestore document snapshot."""
    
    def __init__(self, data):
        self._data = data
    
    @property
    def exists(self):
        return self._data is not None
    
    def to_dict(self):
        return self._data


@pytest.fixture
def fake_db(monkeypatch):
    """Provide a fake Firestore database."""
    from app.api import rate_limiter
    
    fake = FakeFirestore()
    monkeypatch.setattr(rate_limiter, "db", fake)
    return fake


@pytest.fixture
def api_key_data():
    """Provide test API key data."""
    from app.api.auth import APIKey
    
    return APIKey(
        key_hash="test_hash_123",
        name="Test App",
        created_at=datetime.utcnow(),
        is_active=True,
        rate_limit_per_hour=10,  # Low limit for testing
    )


def test_first_request_allowed(fake_db, api_key_data):
    """Test that first request is always allowed."""
    from app.api.rate_limiter import RateLimiter
    
    result = RateLimiter.check_rate_limit(api_key_data)
    assert result is True


def test_within_rate_limit(fake_db, api_key_data):
    """Test requests within rate limit are allowed."""
    from app.api.rate_limiter import RateLimiter
    
    # Make 5 requests (limit is 10)
    for i in range(5):
        result = RateLimiter.check_rate_limit(api_key_data)
        assert result is True, f"Request {i+1} should be allowed"


def test_exceeds_rate_limit(fake_db, api_key_data):
    """Test that requests exceeding rate limit are blocked."""
    from app.api.rate_limiter import RateLimiter
    
    # Make 10 requests (at limit)
    for i in range(10):
        result = RateLimiter.check_rate_limit(api_key_data)
        assert result is True, f"Request {i+1} should be allowed"
    
    # 11th request should be blocked
    result = RateLimiter.check_rate_limit(api_key_data)
    assert result is False, "Request 11 should be blocked"


def test_get_remaining_requests_initial(fake_db, api_key_data):
    """Test getting remaining requests before any requests."""
    from app.api.rate_limiter import RateLimiter
    
    remaining = RateLimiter.get_remaining_requests(api_key_data)
    
    assert remaining["remaining"] == 10
    assert remaining["limit"] == 10


def test_get_remaining_requests_after_use(fake_db, api_key_data):
    """Test getting remaining requests after some usage."""
    from app.api.rate_limiter import RateLimiter
    
    # Make 3 requests
    for _ in range(3):
        RateLimiter.check_rate_limit(api_key_data)
    
    remaining = RateLimiter.get_remaining_requests(api_key_data)
    
    assert remaining["remaining"] == 7
    assert remaining["limit"] == 10


def test_get_remaining_requests_at_limit(fake_db, api_key_data):
    """Test getting remaining requests when at limit."""
    from app.api.rate_limiter import RateLimiter
    
    # Make 10 requests (at limit)
    for _ in range(10):
        RateLimiter.check_rate_limit(api_key_data)
    
    remaining = RateLimiter.get_remaining_requests(api_key_data)
    
    assert remaining["remaining"] == 0
    assert remaining["limit"] == 10


def test_different_api_keys_separate_limits(fake_db):
    """Test that different API keys have separate rate limits."""
    from app.api.rate_limiter import RateLimiter
    from app.api.auth import APIKey
    
    key1 = APIKey(
        key_hash="hash1",
        name="App 1",
        created_at=datetime.utcnow(),
        is_active=True,
        rate_limit_per_hour=5,
    )
    
    key2 = APIKey(
        key_hash="hash2",
        name="App 2",
        created_at=datetime.utcnow(),
        is_active=True,
        rate_limit_per_hour=5,
    )
    
    # Use up key1's limit
    for _ in range(5):
        assert RateLimiter.check_rate_limit(key1) is True
    
    # key1 should be blocked
    assert RateLimiter.check_rate_limit(key1) is False
    
    # key2 should still work
    assert RateLimiter.check_rate_limit(key2) is True

