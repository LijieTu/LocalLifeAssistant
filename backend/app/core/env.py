#!/usr/bin/env python3
"""
Environment loading helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


_DEFAULT_ENV_PATHS: Iterable[Path] = (
    Path("../.env"),
    Path(".env"),
    Path("/app/.env"),
)


def load_environment(paths: Iterable[Path] = _DEFAULT_ENV_PATHS) -> None:
    """
    Load environment variables from a list of candidate paths.

    Stops at the first successful load.
    """
    for path in paths:
        if load_dotenv(path, override=False):
            return

    # Fallback to default .env resolution if none of the provided paths exist.
    load_dotenv(override=False)


