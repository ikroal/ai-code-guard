"""Tests for ReportChannel ABC, registration, and post_pr_comment."""

from __future__ import annotations

import pytest

from ai_guard.config.models import PrReportConfig
from ai_guard.reporter.channel_base import (
    ChannelError,
    ReportChannel,
    get_channel,
    post_pr_comment,
    register_channel,
)


class TestReportChannelABC:
    """ReportChannel cannot be instantiated directly."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            ReportChannel()  # type: ignore[abstract]

    def test_subclass_must_implement_name_and_send(self) -> None:
        class Incomplete(ReportChannel):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_valid_subclass(self) -> None:
        class Valid(ReportChannel):
            @property
            def name(self) -> str:
                return "test"

            def send(self, markdown: str, config: PrReportConfig) -> None:
                pass

        ch = Valid()
        assert ch.name == "test"


class TestRegisterAndGetChannel:
    """Channel registration and lookup."""

    def test_register_and_get(self) -> None:
        class FakeChannel(ReportChannel):
            @property
            def name(self) -> str:
                return "fake"

            def send(self, markdown: str, config: PrReportConfig) -> None:
                pass

        register_channel(FakeChannel)
        ch = get_channel("fake")
        assert ch.name == "fake"

    def test_get_unknown_platform_raises(self) -> None:
        with pytest.raises(ChannelError, match="unknown-platform"):
            get_channel("unknown-platform")

    def test_get_github_returns_github_channel(self) -> None:
        """GitHubChannel should be auto-registered on import."""
        ch = get_channel("github")
        assert ch.name == "github"


class TestPostPrComment:
    """post_pr_comment is non-blocking (catches errors)."""

    def test_disabled_config_does_nothing(self) -> None:
        """When pr_report.enabled=False, should not attempt to send."""
        config = PrReportConfig(enabled=False)
        # Should not raise regardless of missing env vars
        post_pr_comment(report=None, config=config, locale="en")  # type: ignore[arg-type]

    def test_send_failure_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If channel.send() raises, post_pr_comment catches and warns."""
        from ai_guard.checker.models import CheckReport

        config = PrReportConfig(enabled=True, platform="github")
        report = CheckReport(stage="commit", passed=True)

        # Ensure send will fail (no env vars set)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        monkeypatch.delenv("GITHUB_REF", raising=False)
        monkeypatch.delenv("AI_GUARD_PR_NUMBER", raising=False)

        # Should not raise — catches internally
        post_pr_comment(report=report, config=config, locale="en")
