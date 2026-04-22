"""Tests for ReportChannel ABC and the channel registry.

Dispatch-layer behavior (``report`` with ``non_blocking``) is covered in
:mod:`tests.unit.test_reporter.test_core`.
"""

from __future__ import annotations

import pytest

from ac_guard.reporter.channels import base as channel_base
from ac_guard.reporter.channels.base import (
    ChannelError,
    NoPrContextError,
    ReportChannel,
    get_channel,
    register_channel,
)


class TestReportChannelABC:
    """ReportChannel cannot be instantiated directly."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            ReportChannel()  # type: ignore[abstract]

    def test_subclass_must_implement_output(self) -> None:
        class Incomplete(ReportChannel):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_valid_subclass(self) -> None:
        class Valid(ReportChannel):
            name = "test"

            def output(self, payload: str) -> None:
                pass

        ch = Valid()
        assert ch.name == "test"


class TestRegisterAndGetChannel:
    """Channel registration and lookup."""

    def test_register_and_get(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeChannel(ReportChannel):
            name = "fake-register-test"

            def output(self, payload: str) -> None:
                pass

        # Register without polluting the global registry beyond this test.
        original = dict(channel_base._CHANNELS)
        register_channel(FakeChannel)
        monkeypatch.setattr(channel_base, "_CHANNELS", dict(channel_base._CHANNELS))
        channel_base._CHANNELS.update(original)  # restore baseline after monkeypatch

        ch_cls = get_channel("fake-register-test")
        assert ch_cls is FakeChannel
        assert ch_cls.name == "fake-register-test"

    def test_register_rejects_empty_name(self) -> None:
        class Nameless(ReportChannel):
            def output(self, payload: str) -> None:
                pass

        with pytest.raises(TypeError, match="name"):
            register_channel(Nameless)

    def test_get_unknown_platform_raises(self) -> None:
        with pytest.raises(ChannelError, match="unknown-platform"):
            get_channel("unknown-platform")

    def test_get_github_returns_github_channel(self) -> None:
        """GitHubChannel should be auto-registered on import."""
        cls = get_channel("github")
        assert cls.name == "github"


class TestNoPrContextError:
    """NoPrContextError is a ChannelError subclass (silent-skip semantics)."""

    def test_is_channel_error_subclass(self) -> None:
        assert issubclass(NoPrContextError, ChannelError)
