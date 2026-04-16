"""Preset configuration loader for AI Guard init command.

Loads preset YAML files from the config/defaults/presets/ directory.
Presets provide template configurations for different project scenarios.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

__all__ = ["AVAILABLE_PRESETS", "PresetNotFoundError", "load_preset"]

# Preset files are stored relative to this module's location
_PRESETS_DIR = Path(__file__).parent.parent / "config" / "defaults" / "presets"

# Available preset names
AVAILABLE_PRESETS = ["minimal", "standard", "strict"]


class PresetNotFoundError(Exception):
    """Raised when a requested preset does not exist."""

    def __init__(self, name: str) -> None:
        """Initialize with the preset name that was not found.

        Args:
            name: The preset name that could not be found.
        """
        super().__init__(
            f"Unknown preset: '{name}'. Available presets: {AVAILABLE_PRESETS}"
        )
        self.name = name


def load_preset(name: str) -> dict[str, Any]:
    """Load a preset configuration from YAML file.

    Args:
        name: Preset name (minimal, standard, or strict).

    Returns:
        Parsed configuration dict from the preset file.

    Raises:
        PresetNotFoundError: The requested preset name does not exist.
    """
    preset_path = _PRESETS_DIR / f"{name}.yaml"

    if not preset_path.is_file():
        raise PresetNotFoundError(name)

    with preset_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Handle empty files
    return data if data is not None else {}
