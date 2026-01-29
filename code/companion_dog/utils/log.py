"""Logging helper used across the PetFollower modules."""
from __future__ import annotations

import logging
from pathlib import Path

from .config import config

LOG_PATH = Path(config.logging.log_path)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("pet_follower")
if not logger.handlers:
    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

__all__ = ["logger"]
