"""Generator data models for AI Code Guard.

Defines the ``Installation`` record that tracks what was installed
during ``ac-guard install`` / ``ac-guard update``, enabling subsequent
``update`` / ``uninstall`` / ``status`` operations.

FileSpec lives in ac_guard.domain (shared across modules).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

__all__ = [
    "Installation",
    "installation_path",
]

# Internal constant — callers use ``installation_path()`` instead.
_STATE_FILE: str = ".ac-guard/state.json"


def installation_path(project_root: Path) -> Path:
    """Return the path to the installation state file.

    The result is a plain ``Path`` computation with **no** side-effects
    (the parent directory is *not* created).

    Args:
        project_root: Path to the project root.

    Returns:
        Absolute path to ``.ac-guard/state.json``.
    """
    return project_root / _STATE_FILE


@dataclass
class Installation:
    """Installation state record for AI Code Guard.

    Stored in ``.ac-guard/state.json`` to track what was installed,
    enabling update and uninstall operations.

    Attributes:
        ac_guard_version: Tool version at install time.
        installed_agents: List of installed agent identifiers.
        config_hash: SHA hash of guard.yaml at install time.
        installed_at: ISO timestamp of installation.
        artifacts: List of generated file paths (relative to project root).
    """

    ac_guard_version: str
    installed_agents: list[str] = field(default_factory=list)
    config_hash: str = ""
    installed_at: datetime = field(default_factory=datetime.now)
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary suitable for JSON serialization."""
        return {
            "ac_guard_version": self.ac_guard_version,
            "installed_agents": self.installed_agents,
            "config_hash": self.config_hash,
            "installed_at": self.installed_at.isoformat(),
            "artifacts": self.artifacts,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> Installation:
        """Create from dictionary (parsed from JSON)."""
        installed_at = data.get("installed_at")
        if isinstance(installed_at, str):
            installed_at = datetime.fromisoformat(installed_at)
        elif installed_at is None:
            installed_at = datetime.now()
        return cls(
            ac_guard_version=data.get("ac_guard_version", "0.1.0"),
            installed_agents=data.get("installed_agents", []),
            config_hash=data.get("config_hash", ""),
            installed_at=installed_at,
            artifacts=data.get("artifacts", []),
        )

    @classmethod
    def from_json(cls, json_str: str) -> Installation:
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
