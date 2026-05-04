"""Generator error types for AI Code Guard.

Defines a hierarchy of exceptions for artifact generation and writing.
All generator-related errors inherit from GeneratorError, allowing
callers to catch broadly or handle specific failure modes.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ArtifactWriteError",
    "GeneratorError",
]


class GeneratorError(Exception):
    """Base exception for all generator errors."""


@dataclass
class ArtifactWriteError(GeneratorError):
    """Raised when artifact file write fails due to permissions.

    Attributes:
        failed_paths: List of file paths that could not be written.
    """

    failed_paths: list[str]

    def __str__(self) -> str:
        paths_str = ", ".join(self.failed_paths)
        return f"Failed to write artifacts (permission denied): {paths_str}"
