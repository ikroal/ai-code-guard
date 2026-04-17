"""Generator error types for AI Code Guard.

Defines a hierarchy of exceptions for artifact generation and writing.
All generator-related errors inherit from GeneratorError, allowing
callers to catch broadly or handle specific failure modes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "AdapterNotRegisteredError",
    "ArtifactWriteError",
    "GeneratorError",
    "GitDirectoryNotFoundError",
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


class GitDirectoryNotFoundError(GeneratorError):
    """Raised when .git directory does not exist.

    This is a warning-level error — Git Hooks installation is skipped
    but other artifact generation continues.

    Attributes:
        project_root: The project root where .git was expected.
    """

    def __init__(self, project_root: Path) -> None:
        """Initialize with the project root path.

        Args:
            project_root: The project root directory.
        """
        self.project_root = project_root
        super().__init__(
            f".git directory not found in {project_root}. "
            "Git Hooks installation skipped."
        )


@dataclass
class AdapterNotRegisteredError(GeneratorError):
    """Raised when requested agent adapter is not in registry.

    Attributes:
        agent_name: The agent name that was requested.
        available_agents: List of registered agent names.
    """

    agent_name: str
    available_agents: list[str]

    def __str__(self) -> str:
        available_str = ", ".join(self.available_agents)
        return (
            f"Agent adapter '{self.agent_name}' not registered. "
            f"Available agents: {available_str}"
        )
