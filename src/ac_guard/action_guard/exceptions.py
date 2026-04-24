"""Action guard exception types."""

from __future__ import annotations

__all__ = ["ActionGuardError", "PolicyCorruptError"]


class ActionGuardError(Exception):
    """Base exception for all Action guard errors."""


class PolicyCorruptError(ActionGuardError):
    """Raised when runtime.json cannot be parsed.

    Attributes:
        path: Path to the corrupted policy file.
        detail: Original parse error message.
    """

    def __init__(self, path: str, detail: str = "") -> None:
        """Initialize with path and parse error detail.

        Args:
            path: Path to the corrupted policy file.
            detail: Original parse error message.
        """
        self.path = path
        self.detail = detail
        super().__init__(f"Corrupted policy file: {path}. {detail}")
