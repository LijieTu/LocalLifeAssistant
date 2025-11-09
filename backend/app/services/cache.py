#!/usr/bin/env python3
"""
Caching utilities for city event data.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from firebase_admin import firestore  # type: ignore

from ..firebase_config import db

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    city: str
    events: List[Dict[str, Any]]
    cached_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "city": self.city,
            "events": self.events,
            "cached_at": self.cached_at.isoformat(),
            "count": len(self.events),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["CacheEntry"]:
        try:
            cached_at_raw = data.get("cached_at")
            if not cached_at_raw:
                return None
            cached_at = datetime.fromisoformat(str(cached_at_raw))
            return cls(
                city=str(data.get("city")),
                events=list(data.get("events", [])),
                cached_at=cached_at,
                metadata=dict(data.get("metadata", {})),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to restore cache entry: %s", exc)
            return None


class CacheStore:
    """Facade that manages cache persistence across memory, disk, and Firestore."""

    def __init__(
        self,
        *,
        ttl: timedelta,
        cache_dir: Path,
        firestore_client: firestore.Client,
    ) -> None:
        self.ttl = ttl
        self.cache_dir = cache_dir
        self.firestore_client = firestore_client
        self.memory_store: Dict[str, CacheEntry] = {}

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self, city: str) -> Optional[CacheEntry]:
        key = self._key(city)

        entry = self.memory_store.get(key)
        if entry and self._is_valid(entry):
            return entry

        entry = self._load_from_disk(key)
        if entry and self._is_valid(entry):
            self.memory_store[key] = entry
            return entry

        entry = self._load_from_firestore(key)
        if entry and self._is_valid(entry):
            self.memory_store[key] = entry
            self._save_to_disk(key, entry)
            return entry

        return None

    def save(self, city: str, events: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> CacheEntry:
        key = self._key(city)
        entry = CacheEntry(
            city=city,
            events=events,
            cached_at=datetime.now(),
            metadata=metadata or {},
        )
        self.memory_store[key] = entry
        self._save_to_disk(key, entry)
        self._save_to_firestore_async(key, entry)
        return entry

    def invalidate(self, city: str) -> None:
        key = self._key(city)
        self.memory_store.pop(key, None)
        disk_path = self._disk_path(key)
        if disk_path.exists():
            disk_path.unlink()
        try:
            self.firestore_client.collection("event_cache").document(key).delete()
        except Exception:  # pragma: no cover - best-effort
            logger.debug("Failed to delete Firestore cache for %s", key)

    def stats(self) -> Dict[str, Any]:
        return {
            "local_memory": {
                "total": len(self.memory_store),
                "valid": sum(1 for entry in self.memory_store.values() if self._is_valid(entry)),
            },
            "local_disk": self._disk_stats(),
            "firebase": self._firestore_stats(),
            "ttl_hours": self.ttl.total_seconds() / 3600,
            "cache_dir": str(self.cache_dir),
            "storage_type": "hybrid_local_firebase",
        }

    def cleanup(self) -> None:
        expired_keys = [key for key, entry in self.memory_store.items() if not self._is_valid(entry)]
        for key in expired_keys:
            del self.memory_store[key]

        for path in self.cache_dir.glob("*.json"):
            entry = self._load_from_disk(path.stem)
            if entry is None or not self._is_valid(entry):
                try:
                    path.unlink()
                except OSError:
                    logger.debug("Failed to remove cache file %s", path)

        try:
            docs = self.firestore_client.collection("event_cache").get()
            for doc in docs:
                data = doc.to_dict()
                entry = CacheEntry.from_dict(data or {})
                if not entry or not self._is_valid(entry):
                    doc.reference.delete()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Firestore cleanup failed: %s", exc)

    # Internal helpers

    def _key(self, city: str) -> str:
        return city.lower().replace(" ", "_").replace("/", "_")

    def _disk_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _is_valid(self, entry: CacheEntry) -> bool:
        age = datetime.now() - entry.cached_at
        return age < self.ttl

    def _load_from_disk(self, key: str) -> Optional[CacheEntry]:
        path = self._disk_path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return CacheEntry.from_dict(data)
        except Exception as exc:
            logger.debug("Failed to read disk cache for %s: %s", key, exc)
            return None

    def _save_to_disk(self, key: str, entry: CacheEntry) -> None:
        path = self._disk_path(key)
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(entry.to_dict(), handle, ensure_ascii=False, indent=2)
        except Exception as exc:  # pragma: no cover - best-effort
            logger.debug("Failed to write disk cache for %s: %s", key, exc)

    def _load_from_firestore(self, key: str) -> Optional[CacheEntry]:
        try:
            doc = self.firestore_client.collection("event_cache").document(key).get()
            if not doc.exists:
                return None
            return CacheEntry.from_dict(doc.to_dict() or {})
        except Exception as exc:
            logger.debug("Unable to load Firestore cache for %s: %s", key, exc)
            return None

    def _save_to_firestore_async(self, key: str, entry: CacheEntry) -> None:
        try:
            self.firestore_client.collection("event_cache").document(key).set(entry.to_dict())
        except Exception as exc:  # pragma: no cover - best-effort
            logger.debug("Failed to store Firestore cache for %s: %s", key, exc)

    def _disk_stats(self) -> Dict[str, int]:
        total = 0
        valid = 0
        for path in self.cache_dir.glob("*.json"):
            total += 1
            entry = self._load_from_disk(path.stem)
            if entry and self._is_valid(entry):
                valid += 1
        return {"total": total, "valid": valid}

    def _firestore_stats(self) -> Dict[str, int]:
        total = 0
        valid = 0
        try:
            docs = self.firestore_client.collection("event_cache").get()
            for doc in docs:
                total += 1
                entry = CacheEntry.from_dict(doc.to_dict() or {})
                if entry and self._is_valid(entry):
                    valid += 1
        except Exception:  # pragma: no cover - best-effort
            logger.debug("Failed to compute Firestore cache stats")
        return {"total": total, "valid": valid}


def create_cache_store(ttl_hours: int, cache_dir: str = "./cache") -> CacheStore:
    return CacheStore(
        ttl=timedelta(hours=ttl_hours),
        cache_dir=Path(cache_dir),
        firestore_client=db,
    )


