"""Tests for preset configuration loader."""

from __future__ import annotations

import pytest

from ac_guard.cli.presets import (
    AVAILABLE_PRESETS,
    PresetNotFoundError,
    load_preset,
)


class TestLoadPreset:
    """Tests for load_preset function."""

    def test_load_preset_minimal(self) -> None:
        """Load minimal preset successfully."""
        config = load_preset("minimal")
        assert isinstance(config, dict)
        assert "code" in config
        assert config["code"]["commit"]["format"] is True
        assert config["output"]["audit"]["enabled"] is False

    def test_load_preset_standard(self) -> None:
        """Load standard preset successfully."""
        config = load_preset("standard")
        assert isinstance(config, dict)
        assert "code" in config
        assert config["code"]["commit"]["format"] is True
        # naming shortcut is not shipped in presets (see issue #95)
        assert "naming" not in config["code"]["commit"]
        assert config["code"]["push"]["lint"] is True
        assert config["output"]["audit"]["enabled"] is True

    def test_load_preset_strict(self) -> None:
        """Load strict preset successfully."""
        config = load_preset("strict")
        assert isinstance(config, dict)
        assert "behavior" in config
        assert "write" in config["behavior"]
        assert len(config["behavior"]["write"]["forbidden"]) > 0
        assert config["output"]["pr_report"]["enabled"] is True

    def test_load_preset_unknown_raises(self) -> None:
        """Unknown preset raises PresetNotFoundError."""
        with pytest.raises(PresetNotFoundError) as exc_info:
            load_preset("nonexistent")
        assert "nonexistent" in str(exc_info.value)
        assert "Available presets" in str(exc_info.value)

    def test_load_preset_empty_name_raises(self) -> None:
        """Empty preset name raises PresetNotFoundError."""
        with pytest.raises(PresetNotFoundError):
            load_preset("")


class TestAvailablePresets:
    """Tests for AVAILABLE_PRESETS constant."""

    def test_available_presets_is_list(self) -> None:
        """AVAILABLE_PRESETS is a list."""
        assert isinstance(AVAILABLE_PRESETS, list)

    def test_available_presets_contains_expected(self) -> None:
        """AVAILABLE_PRESETS contains expected preset names."""
        assert "minimal" in AVAILABLE_PRESETS
        assert "standard" in AVAILABLE_PRESETS
        assert "strict" in AVAILABLE_PRESETS

    def test_available_presets_count(self) -> None:
        """AVAILABLE_PRESETS has exactly 3 presets."""
        assert len(AVAILABLE_PRESETS) == 3


class TestPresetNotFoundError:
    """Tests for PresetNotFoundError exception."""

    def test_exception_message_contains_name(self) -> None:
        """Exception message contains the preset name."""
        exc = PresetNotFoundError("invalid")
        assert "invalid" in str(exc)
        assert exc.name == "invalid"

    def test_exception_is_runtime_error_subclass(self) -> None:
        """PresetNotFoundError is an Exception subclass."""
        assert issubclass(PresetNotFoundError, Exception)
