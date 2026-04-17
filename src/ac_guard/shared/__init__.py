"""Shared types module for AI Code Guard.

Contains types shared across adapters, generator, and other modules.
"""

from ac_guard.shared.types import (
    MARKER_BEGIN,
    MARKER_END,
    FileSpec,
    wrap_with_managed_block,
)

__all__ = [
    "FileSpec",
    "MARKER_BEGIN",
    "MARKER_END",
    "wrap_with_managed_block",
]
