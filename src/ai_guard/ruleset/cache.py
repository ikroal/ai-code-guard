"""Ruleset cache management for AI Guard.

Provides functions to list, inspect, and clear the local ruleset
cache stored under ``.ai-guard/cache/``.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from ai_guard.ruleset.models import CACHE_DIR

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["clear_cache", "get_cache_dir", "list_cached"]


def get_cache_dir(project_root: Path) -> Path:
    """Return the cache directory path, creating it if needed.

    Args:
        project_root: Path to the project root.

    Returns:
        Path to ``.ai-guard/cache/``.
    """
    cache = project_root / CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def list_cached(project_root: Path) -> list[str]:
    """List names of cached rulesets.

    Args:
        project_root: Path to the project root.

    Returns:
        Sorted list of ruleset directory names. Empty list if the
        cache directory does not exist.
    """
    cache = project_root / CACHE_DIR
    if not cache.is_dir():
        return []
    return sorted(p.name for p in cache.iterdir() if p.is_dir())


def clear_cache(project_root: Path) -> int:
    """Remove all cached rulesets.

    The cache directory itself is preserved; only its contents
    (ruleset subdirectories) are removed.

    Args:
        project_root: Path to the project root.

    Returns:
        Number of rulesets removed.
    """
    cache = project_root / CACHE_DIR
    if not cache.is_dir():
        return 0

    count = 0
    for entry in cache.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
            count += 1
    return count
