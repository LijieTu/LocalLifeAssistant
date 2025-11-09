#!/usr/bin/env python3
"""
Logging utilities for the backend application.
"""

from __future__ import annotations

import logging
from typing import Optional


def configure_logging(level: Optional[int] = None) -> None:
    """
    Configure root logger.

    Parameters
    ----------
    level:
        Logging level to apply. Defaults to logging.INFO when not provided.
    """
    if level is None:
        level = logging.INFO

    if not logging.getLogger().handlers:
        logging.basicConfig(level=level)
    else:
        logging.getLogger().setLevel(level)


