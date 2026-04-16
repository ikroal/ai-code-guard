"""Tests for enforcer __main__ module."""

from __future__ import annotations

from ai_guard.enforcer.__main__ import main


class TestMain:
    """Tests for __main__ entry point."""

    def test_main_is_callable(self) -> None:
        """main function is importable and callable."""
        assert callable(main)
