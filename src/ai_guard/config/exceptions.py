"""Configuration error types for AI Guard.

Defines a hierarchy of exceptions for config loading and validation.
All config-related errors inherit from ConfigError, allowing callers
to catch broadly or handle specific failure modes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigSyntaxError",
    "ConfigValidationError",
    "ConfigWarning",
    "ValidationIssue",
]


@dataclass
class ValidationIssue:
    """A single validation problem found in a config file.

    Attributes:
        path: Dot-notation field path where the issue was found
            (e.g. "behavior.read.forbidden[0].pattern").
        message: Human-readable description of the problem.
        value: The offending value, if applicable.
    """

    path: str
    message: str
    value: Any = None


class ConfigWarning(UserWarning):
    """Warning for non-fatal config merge issues.

    Emitted when a ``remove`` target is not found (possible typo)
    or when a ``remove`` targets a system-protected rule.
    """


class ConfigError(Exception):
    """Base exception for all configuration errors."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when the config file does not exist.

    Attributes:
        path: The file path that was not found.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize with the path that was not found.

        Args:
            path: The file path that was searched.
        """
        self.path = Path(path)
        super().__init__(
            f"Config file not found: {self.path}. Run 'ai-guard init' to generate one."
        )


class ConfigSyntaxError(ConfigError):
    """Raised when YAML parsing fails.

    Attributes:
        path: The file path that failed to parse.
        line: Line number of the error (1-based), or None.
        column: Column number of the error (1-based), or None.
        detail: The original parser error message.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        line: int | None = None,
        column: int | None = None,
        detail: str = "",
    ) -> None:
        """Initialize with parsing error details.

        Args:
            path: The file path that failed to parse.
            line: Line number of the error (1-based), or None.
            column: Column number of the error (1-based), or None.
            detail: The original parser error message.
        """
        self.path = Path(path)
        self.line = line
        self.column = column
        self.detail = detail
        location = f"{self.path}"
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        super().__init__(f"YAML syntax error in {location}: {detail}")


class ConfigValidationError(ConfigError):
    """Raised when schema or semantic validation fails.

    Collects all validation issues before raising, so the user
    can fix every problem in one pass.

    Attributes:
        errors: All validation issues found.
    """

    def __init__(self, errors: list[ValidationIssue]) -> None:
        """Initialize with all collected validation issues.

        Args:
            errors: List of ValidationIssue objects describing
                each validation problem found.
        """
        self.errors = errors
        count = len(errors)
        summary = f"Config validation failed with {count} error(s):"
        details = "\n".join(f"  - {e.path}: {e.message}" for e in errors)
        super().__init__(f"{summary}\n{details}")
