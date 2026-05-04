"""Contract tests locking the public surface of ``ac_guard.cli``.

The CLI is the shell-facing boundary; its sole public symbol is the
Typer ``app`` consumed by the ``ac-guard`` console_script. These tests
fail loudly if anything else is re-exported through the package facade.
"""

from __future__ import annotations

import typer

import ac_guard.cli as cli

_EXPECTED_PUBLIC_API: frozenset[str] = frozenset({"app"})


def test_public_api_exact() -> None:
    """``__all__`` must be exactly ``{"app"}``."""
    assert set(cli.__all__) == _EXPECTED_PUBLIC_API


def test_app_is_typer_instance() -> None:
    """``cli.app`` must be the Typer dispatch root."""
    assert isinstance(cli.app, typer.Typer)


def test_demoted_symbols_not_in_public_api() -> None:
    """Symbols that used to be re-exported must no longer appear here.

    These belong to internal command/preset helpers; tests that need
    them deep-import from the relevant submodule (mirrors the
    ``ruleset`` / ``generator`` precedent).
    """
    for name in (
        "init_command",
        "load_preset",
        "AVAILABLE_PRESETS",
    ):
        assert name not in cli.__all__, f"{name} should be demoted"
