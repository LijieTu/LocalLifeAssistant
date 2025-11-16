#!/usr/bin/env python3
"""
Tests for API key authentication.
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
    
    @property
    def exists(self):
        return self.doc_id in self.data


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
    # Import here to avoid Firebase initialization
    from app.api import auth
    
    fake = FakeFirestore()
    monkeypatch.setattr(auth, "db", fake)
    return fake


def test_generate_key():
    """Test API key generation."""
    from app.api.auth import APIKeyManager
    
    key = APIKeyManager.generate_key()
    assert key.startswith("loco_")
    assert len(key) > 10


def test_hash_key():
    """Test API key hashing."""
    from app.api.auth import APIKeyManager
    
    key = "test_key_123"
    hash1 = APIKeyManager.hash_key(key)
    hash2 = APIKeyManager.hash_key(key)
    
    # Same key should produce same hash
    assert hash1 == hash2
    
    # Different keys should produce different hashes
    hash3 = APIKeyManager.hash_key("different_key")
    assert hash1 != hash3


def test_create_api_key(fake_db):
    """Test creating a new API key."""
    from app.api.auth import APIKeyManager
    
    key = APIKeyManager.create_api_key("Test App", rate_limit_per_hour=200)
    
    assert key.startswith("loco_")
    
    # Verify key was stored
    key_hash = APIKeyManager.hash_key(key)
    stored_data = fake_db.data["api_keys"][key_hash]
    
    assert stored_data["name"] == "Test App"
    assert stored_data["rate_limit_per_hour"] == 200
    assert stored_data["is_active"] is True


def test_verify_valid_key(fake_db):
    """Test verifying a valid API key."""
    from app.api.auth import APIKeyManager
    
    key = APIKeyManager.create_api_key("Test App")
    
    result = APIKeyManager.verify_key(key)
    
    assert result is not None
    assert result.name == "Test App"
    assert result.is_active is True


def test_verify_invalid_key(fake_db):
    """Test verifying an invalid API key."""
    from app.api.auth import APIKeyManager
    
    result = APIKeyManager.verify_key("invalid_key_123")
    assert result is None


def test_verify_revoked_key(fake_db):
    """Test verifying a revoked API key."""
    from app.api.auth import APIKeyManager
    
    key = APIKeyManager.create_api_key("Test App")
    
    # Revoke the key
    APIKeyManager.revoke_key(key)
    
    # Should return None for revoked key
    result = APIKeyManager.verify_key(key)
    assert result is None


def test_revoke_key(fake_db):
    """Test revoking an API key."""
    from app.api.auth import APIKeyManager
    
    key = APIKeyManager.create_api_key("Test App")
    
    # Revoke should succeed
    success = APIKeyManager.revoke_key(key)
    assert success is True
    
    # Verify key is inactive
    key_hash = APIKeyManager.hash_key(key)
    stored_data = fake_db.data["api_keys"][key_hash]
    assert stored_data["is_active"] is False


def test_revoke_nonexistent_key(fake_db):
    """Test revoking a non-existent API key."""
    from app.api.auth import APIKeyManager
    
    success = APIKeyManager.revoke_key("nonexistent_key")
    assert success is False

