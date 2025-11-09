#!/usr/bin/env python3

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Dict

import pytest

from backend.app.services.cache import CacheStore, CacheEntry


class FakeDocumentSnapshot:
    def __init__(self, key: str, data: Dict[str, Any], bucket: Dict[str, Dict[str, Any]]):
        self._key = key
        self._data = data
        self.reference = FakeDocumentRef(bucket, key)

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Dict[str, Any]:
        return self._data


class FakeDocumentRef:
    def __init__(self, bucket: Dict[str, Dict[str, Any]], key: str):
        self._bucket = bucket
        self._key = key

    def set(self, data: Dict[str, Any]) -> None:
        self._bucket[self._key] = data

    def get(self) -> FakeDocumentSnapshot:
        data = self._bucket.get(self._key)
        return FakeDocumentSnapshot(self._key, data, self._bucket)

    def delete(self) -> None:
        self._bucket.pop(self._key, None)


class FakeCollection:
    def __init__(self, store: Dict[str, Dict[str, Any]]):
        self._store = store

    def document(self, key: str) -> FakeDocumentRef:
        return FakeDocumentRef(self._store, key)

    def get(self) -> list[FakeDocumentSnapshot]:
        return [FakeDocumentSnapshot(key, data, self._store) for key, data in list(self._store.items())]


class FakeFirestore:
    def __init__(self):
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def collection(self, name: str) -> FakeCollection:
        bucket = self._collections.setdefault(name, {})
        return FakeCollection(bucket)


def test_cache_store_save_and_load(tmp_path: Path) -> None:
    firestore = FakeFirestore()
    store = CacheStore(ttl=timedelta(hours=6), cache_dir=tmp_path, firestore_client=firestore)

    events = [{"title": "Art Walk"}]
    store.save("San Francisco", events)

    loaded = store.load("San Francisco")
    assert loaded is not None
    assert loaded.events == events
    assert loaded.city == "San Francisco"

    # ensure persisted to Firestore stub
    collection = firestore.collection("event_cache")
    doc = collection.document("san_francisco").get()
    assert doc.exists
    assert doc.to_dict()["count"] == 1


def test_cache_store_respects_ttl(tmp_path: Path) -> None:
    firestore = FakeFirestore()
    store = CacheStore(ttl=timedelta(seconds=0), cache_dir=tmp_path, firestore_client=firestore)

    store.save("New York", [{"title": "Concert"}])

    # Entry should be considered expired immediately
    assert store.load("New York") is None

    # Cleanup removes persisted artifacts
    store.cleanup()
    assert not any(tmp_path.glob("*.json"))
    assert not firestore.collection("event_cache").get()


