"""Ruleset cache management for AI Code Guard.

Provides functions to list, inspect, and clear the local ruleset
cache stored under ``.ac-guard/cache/``, and to access individual
cached ruleset directories and their ``guard.yaml`` content.
"""

from __future__ import annotations

import json
import shutil
import stat
from typing import TYPE_CHECKING, Any

import yaml

from ac_guard.ruleset.models import CACHE_DIR

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "clear_cache",
    "get_cache_dir",
    "get_ruleset_dir",
    "list_cached",
    "load_ruleset_config",
    "read_meta",
]


def get_cache_dir(project_root: Path) -> Path:
    """Return the cache directory path, creating it if needed.

    Args:
        project_root: Path to the project root.

    Returns:
        Path to ``.ac-guard/cache/``.
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


def get_ruleset_dir(project_root: Path, name: str) -> Path | None:
    """Return the cached directory for a single ruleset, or ``None``.

    A ruleset is considered "cached" when its directory exists under
    ``<project_root>/.ac-guard/cache/<name>/``. Missing cache root,
    missing ruleset, or a path that exists but is not a directory all
    map to ``None`` — callers decide how to react.

    Args:
        project_root: Path to the project root.
        name: Ruleset directory name.

    Returns:
        Path to the cached ruleset directory if present, else ``None``.
    """
    candidate = project_root / CACHE_DIR / name
    return candidate if candidate.is_dir() else None


def load_ruleset_config(project_root: Path, name: str) -> dict[str, Any] | None:
    """Load a cached ruleset's ``guard.yaml`` as a raw dict.

    Returns ``None`` when the ruleset is not cached, when its
    ``guard.yaml`` is missing or unreadable, or when the YAML payload
    parses to anything other than a mapping. No schema validation is
    performed — that responsibility lives in :mod:`ac_guard.config`.

    Args:
        project_root: Path to the project root.
        name: Ruleset directory name.

    Returns:
        The parsed ``guard.yaml`` dict, or ``None`` when unavailable.
    """
    ruleset_dir = get_ruleset_dir(project_root, name)
    if ruleset_dir is None:
        return None

    guard_yaml = ruleset_dir / "guard.yaml"
    if not guard_yaml.is_file():
        return None

    data = yaml.safe_load(guard_yaml.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return data


def read_meta(project_root: Path, name: str) -> dict[str, Any] | None:
    """Read ``.ruleset-meta.json`` for a cached ruleset.

    Args:
        project_root: Path to the project root.
        name: Ruleset directory name.

    Returns:
        Parsed metadata dict, or None if the file does not exist.
    """
    meta_path = project_root / CACHE_DIR / name / ".ruleset-meta.json"
    if not meta_path.is_file():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


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
            shutil.rmtree(entry, onerror=_rm_readonly)
            count += 1
    return count


def _rm_readonly(_func: object, path: str, _exc_info: object) -> None:
    """Error handler for shutil.rmtree on read-only files (Windows .git)."""
    import pathlib

    pathlib.Path(path).chmod(stat.S_IWRITE)
    pathlib.Path(path).unlink()
