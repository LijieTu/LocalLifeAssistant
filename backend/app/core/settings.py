#!/usr/bin/env python3
"""
Application settings and configuration helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
from typing import List


_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

_RENDER_FRONTEND_DOMAIN = "https://locallifeassistant-frontend.onrender.com"


@dataclass
class Settings:
    """Container for runtime configuration."""

    domain_name: str = field(default_factory=lambda: os.getenv("DOMAIN_NAME", "").strip())
    cache_ttl_hours: int = field(default_factory=lambda: int(os.getenv("CACHE_TTL_HOURS", "6")))
    render_frontend_domain: str = _RENDER_FRONTEND_DOMAIN
    _dev_origins: List[str] = field(default_factory=lambda: list(_DEV_ORIGINS))

    def allowed_origins(self) -> List[str]:
        """Compute allowed CORS origins."""
        origins: List[str]
        if self.domain_name and self.domain_name not in {"your-domain.com", "localhost"}:
            origins = [
                f"http://{self.domain_name}",
                f"https://{self.domain_name}",
                f"https://www.{self.domain_name}",
            ]
        else:
            origins = list(self._dev_origins)

        if self.render_frontend_domain and self.render_frontend_domain not in origins:
            origins.append(self.render_frontend_domain)

        return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


