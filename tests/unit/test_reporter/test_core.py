"""Tests for :mod:`ac_guard.reporter.core` dispatch + validation."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from ac_guard.domain.models import CheckResult, StageOutcome, Violation
from ac_guard.reporter import (
    ChannelError,
    FileCfg,
    FormatKind,
    GitPlatformCfg,
    NoPrContextError,
    ReportConfig,
    TerminalCfg,
    report,
)
from ac_guard.reporter.channels import base as channel_base
from ac_guard.reporter.channels.base import ReportChannel

if TYPE_CHECKING:
    from pathlib import Path


def _passed_outcome() -> StageOutcome:
    return StageOutcome(
        stage="pre-commit",
        passed=True,
        results=[CheckResult(name="format", passed=True, duration_ms=10)],
        duration_ms=10,
    )


def _failed_outcome() -> StageOutcome:
    return StageOutcome(
        stage="pre-push",
        passed=False,
        results=[
            CheckResult(
                name="lint",
                passed=False,
                violations=[Violation(file="a.py", line=1, message="E1")],
            ),
        ],
        duration_ms=5,
    )


# ---------------------------------------------------------------------------
# Valid dispatch matrix (channel x format combinations that must work)
# ---------------------------------------------------------------------------


class TestValidDispatch:
    """All permitted (channel, format) pairs deliver without error."""

    def test_terminal_text(self) -> None:
        buf = io.StringIO()
        report(
            _passed_outcome(),
            ReportConfig(
                channel=TerminalCfg(stream=buf),
                format=FormatKind.TEXT,
            ),
        )
        out = buf.getvalue()
        # Multi-line text rendering: stage heading + check indicator.
        assert "pre-commit" in out
        assert "✅" in out

    def test_terminal_json(self) -> None:
        buf = io.StringIO()
        report(
            _passed_outcome(),
            ReportConfig(channel=TerminalCfg(stream=buf), format=FormatKind.JSON),
        )
        out = buf.getvalue()
        assert '"stage": "pre-commit"' in out
        assert '"passed": true' in out

    def test_file_text(self, tmp_path: Path) -> None:
        target = tmp_path / "report.txt"
        report(
            _passed_outcome(),
            ReportConfig(channel=FileCfg(path=target), format=FormatKind.TEXT),
        )
        text = target.read_text(encoding="utf-8")
        assert "pre-commit" in text
        assert "✅" in text

    def test_file_markdown(self, tmp_path: Path) -> None:
        target = tmp_path / "report.md"
        report(
            _passed_outcome(),
            ReportConfig(channel=FileCfg(path=target), format=FormatKind.MARKDOWN),
        )
        text = target.read_text(encoding="utf-8")
        # format_markdown template uses ✅/❌ emoji indicators.
        assert "✅" in text or "❌" in text

    def test_file_json(self, tmp_path: Path) -> None:
        target = tmp_path / "report.json"
        report(
            _passed_outcome(),
            ReportConfig(channel=FileCfg(path=target), format=FormatKind.JSON),
        )
        text = target.read_text(encoding="utf-8")
        assert '"stage": "pre-commit"' in text

    def test_git_platform_markdown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Git-platform channel gets Markdown payload, invokes output()."""
        called: dict[str, str] = {}

        class _FakeGit(ReportChannel):
            name = "fake-dispatch-git"

            def __init__(self, config: object) -> None:
                pass

            def output(self, payload: str) -> None:
                called["payload"] = payload

        monkeypatch.setitem(channel_base._CHANNELS, "fake-dispatch-git", _FakeGit)

        report(
            _failed_outcome(),
            ReportConfig(
                channel=GitPlatformCfg(platform="fake-dispatch-git"),
                format=FormatKind.MARKDOWN,
            ),
        )
        # Payload was the Markdown rendering (contains the stage line).
        assert "payload" in called
        assert "pre-push" in called["payload"]


# ---------------------------------------------------------------------------
# Invalid combinations rejected upfront
# ---------------------------------------------------------------------------


class TestInvalidCombinations:
    """Unsupported (channel, format) pairs must raise ValueError."""

    def test_terminal_markdown_rejected(self) -> None:
        with pytest.raises(ValueError, match="TerminalCfg"):
            report(
                _passed_outcome(),
                ReportConfig(channel=TerminalCfg(), format=FormatKind.MARKDOWN),
            )

    def test_git_platform_text_rejected(self) -> None:
        with pytest.raises(ValueError, match="GitPlatformCfg"):
            report(
                _passed_outcome(),
                ReportConfig(
                    channel=GitPlatformCfg(platform="github"),
                    format=FormatKind.TEXT,
                ),
            )

    def test_git_platform_json_rejected(self) -> None:
        with pytest.raises(ValueError, match="GitPlatformCfg"):
            report(
                _passed_outcome(),
                ReportConfig(
                    channel=GitPlatformCfg(platform="github"),
                    format=FormatKind.JSON,
                ),
            )


# ---------------------------------------------------------------------------
# non_blocking semantics
# ---------------------------------------------------------------------------


class TestNonBlocking:
    """non_blocking=True swallows delivery failures."""

    def test_no_pr_context_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """NoPrContextError from the channel → silent (no stderr, no raise)."""

        class _NoPr(ReportChannel):
            name = "fake-no-pr"

            def __init__(self, config: object) -> None:
                pass

            def output(self, payload: str) -> None:
                raise NoPrContextError("no PR")

        monkeypatch.setitem(channel_base._CHANNELS, "fake-no-pr", _NoPr)

        report(
            _passed_outcome(),
            ReportConfig(
                channel=GitPlatformCfg(platform="fake-no-pr"),
                format=FormatKind.MARKDOWN,
            ),
            non_blocking=True,
        )
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_other_channel_error_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-NoPrContext ChannelError → stderr warning, no raise."""

        class _ApiFail(ReportChannel):
            name = "fake-api-500"

            def __init__(self, config: object) -> None:
                pass

            def output(self, payload: str) -> None:
                raise ChannelError("API 500")

        monkeypatch.setitem(channel_base._CHANNELS, "fake-api-500", _ApiFail)

        report(
            _passed_outcome(),
            ReportConfig(
                channel=GitPlatformCfg(platform="fake-api-500"),
                format=FormatKind.MARKDOWN,
            ),
            non_blocking=True,
        )
        captured = capsys.readouterr()
        assert "report delivery failed" in captured.err
        assert "API 500" in captured.err

    def test_default_non_blocking_false_propagates_no_pr_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """non_blocking defaults to False → NoPrContextError propagates."""

        class _NoPr(ReportChannel):
            name = "fake-no-pr-raising"

            def __init__(self, config: object) -> None:
                pass

            def output(self, payload: str) -> None:
                raise NoPrContextError("no PR")

        monkeypatch.setitem(channel_base._CHANNELS, "fake-no-pr-raising", _NoPr)

        with pytest.raises(NoPrContextError):
            report(
                _passed_outcome(),
                ReportConfig(
                    channel=GitPlatformCfg(platform="fake-no-pr-raising"),
                    format=FormatKind.MARKDOWN,
                ),
            )

    def test_default_non_blocking_false_propagates_channel_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """non_blocking defaults to False → ChannelError propagates."""

        class _ApiFail(ReportChannel):
            name = "fake-api-500-raising"

            def __init__(self, config: object) -> None:
                pass

            def output(self, payload: str) -> None:
                raise ChannelError("boom")

        monkeypatch.setitem(channel_base._CHANNELS, "fake-api-500-raising", _ApiFail)

        with pytest.raises(ChannelError, match="boom"):
            report(
                _passed_outcome(),
                ReportConfig(
                    channel=GitPlatformCfg(platform="fake-api-500-raising"),
                    format=FormatKind.MARKDOWN,
                ),
            )


# ---------------------------------------------------------------------------
# ReportConfig defaults
# ---------------------------------------------------------------------------


class TestReportConfigDefaults:
    def test_defaults(self) -> None:
        """Unspecified format defaults to TEXT, locale to 'en'."""
        cfg = ReportConfig(channel=TerminalCfg())
        assert cfg.format is FormatKind.TEXT
        assert cfg.locale == "en"


# ---------------------------------------------------------------------------
# TerminalCfg default stream = sys.stdout
# ---------------------------------------------------------------------------


class TestTerminalDefault:
    def test_default_stream_is_sys_stdout(self) -> None:
        """TerminalCfg(stream=None) resolves to sys.stdout in channel."""
        with patch("builtins.print") as mock_print:
            report(
                _passed_outcome(),
                ReportConfig(channel=TerminalCfg(), format=FormatKind.TEXT),
            )
            # print was called at least once (channel writes via print).
            assert mock_print.call_count >= 1
