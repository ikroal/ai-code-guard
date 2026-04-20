"""Shared fixtures for integration tests.

The autouse ``_isolate_cwd`` fixture forces every integration test into
its own ``tmp_path`` before the test body runs. Without it, any test
that invokes a cwd-sensitive command (``ac-guard install`` /
``uninstall`` / ``update``) would operate on the real repository root
and — now that ac-guard dogfoods itself — actively destroy this repo's
own installed hooks and state.

Tests that legitimately need a different working directory can still
call ``monkeypatch.chdir(other_path)`` inside the body; this fixture
only guarantees the default is never the real repo root.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every integration test's cwd to its own tmp_path."""
    monkeypatch.chdir(tmp_path)
