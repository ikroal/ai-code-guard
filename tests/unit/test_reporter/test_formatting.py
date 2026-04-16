"""Tests for Reporter formatting (R1, R2, Markdown)."""

from __future__ import annotations

from ai_guard.checker.models import CheckReport, CheckResult, Violation
from ai_guard.reporter.formatting import format_gate, format_markdown, format_terminal


def _passed_report() -> CheckReport:
    """Create a passing report for testing."""
    return CheckReport(
        stage="commit",
        passed=True,
        results=[
            CheckResult(name="format", passed=True, duration_ms=23),
            CheckResult(name="naming", passed=True, duration_ms=15),
        ],
        duration_ms=38,
    )


def _failed_report() -> CheckReport:
    """Create a failing report with violations."""
    return CheckReport(
        stage="push",
        passed=False,
        results=[
            CheckResult(name="lint", passed=True, duration_ms=50),
            CheckResult(
                name="test",
                passed=False,
                duration_ms=200,
                violations=[
                    Violation(
                        file="src/main.py",
                        line=10,
                        column=5,
                        code="E501",
                        message="line too long",
                        source="ruff",
                    ),
                    Violation(
                        file="src/util.py",
                        line=22,
                        message="unused import",
                        code="F401",
                    ),
                ],
                output="ruff check failed\n",
            ),
        ],
        duration_ms=250,
    )


def _skipped_report() -> CheckReport:
    """Create a report with skipped checks."""
    return CheckReport(
        stage="commit",
        passed=True,
        results=[
            CheckResult(name="format", passed=True, duration_ms=10),
            CheckResult(name="build", passed=True, skipped=True),
        ],
        duration_ms=10,
    )


# ---------------------------------------------------------------------------
# TestFormatTerminal
# ---------------------------------------------------------------------------


class TestFormatTerminal:
    """Tests for format_terminal (R1)."""

    def test_passed_report(self) -> None:
        """Passing report shows PASSED."""
        output = format_terminal(_passed_report())
        assert "PASSED" in output
        assert "commit" in output

    def test_failed_report(self) -> None:
        """Failing report shows FAILED and violation details."""
        output = format_terminal(_failed_report())
        assert "FAILED" in output
        assert "src/main.py:10" in output
        assert "line too long" in output

    def test_skipped_checks(self) -> None:
        """Skipped checks show SKIP indicator."""
        output = format_terminal(_skipped_report())
        assert "SKIP" in output

    def test_violations_shown(self) -> None:
        """Violation file, line, code are displayed."""
        output = format_terminal(_failed_report())
        assert "E501" in output
        assert "src/util.py:22" in output

    def test_verbosity_quiet(self) -> None:
        """Quiet mode shows minimal output."""
        output = format_terminal(_failed_report(), verbosity="quiet")
        assert "FAILED" in output
        # Should not contain per-check details
        assert "[PASS]" not in output
        assert "[FAIL]" not in output

    def test_verbosity_verbose(self) -> None:
        """Verbose mode shows check output."""
        output = format_terminal(_failed_report(), verbosity="verbose")
        assert "ruff check failed" in output

    def test_duration_shown(self) -> None:
        """Duration is displayed."""
        output = format_terminal(_passed_report())
        assert "38ms" in output

    def test_pass_fail_count(self) -> None:
        """Shows pass/fail summary count."""
        output = format_terminal(_failed_report())
        assert "1/2" in output


# ---------------------------------------------------------------------------
# TestFormatGate
# ---------------------------------------------------------------------------


class TestFormatGate:
    """Tests for format_gate (R2)."""

    def test_passed_gate(self) -> None:
        """Passing report returns exit code 0."""
        msg, code = format_gate(_passed_report())
        assert code == 0
        assert "passed" in msg

    def test_failed_gate(self) -> None:
        """Failing report returns exit code 1 with failed check names."""
        msg, code = format_gate(_failed_report())
        assert code == 1
        assert "test" in msg
        assert "failed" in msg


# ---------------------------------------------------------------------------
# TestFormatMarkdown
# ---------------------------------------------------------------------------


class TestFormatMarkdown:
    """Tests for format_markdown."""

    def test_markdown_table(self) -> None:
        """Markdown output contains a results table."""
        md = format_markdown(_passed_report())
        assert "| Check" in md or "| check" in md.lower()
        assert "format" in md

    def test_violations_in_details(self) -> None:
        """Violations are in a collapsible details section."""
        md = format_markdown(_failed_report())
        assert "<details>" in md
        assert "src/main.py" in md

    def test_passed_emoji(self) -> None:
        """Passed report has success emoji."""
        md = format_markdown(_passed_report())
        assert "✅" in md

    def test_failed_emoji(self) -> None:
        """Failed report has failure emoji."""
        md = format_markdown(_failed_report())
        assert "❌" in md

    def test_zh_cn_locale(self) -> None:
        """Chinese locale produces Chinese text."""
        md = format_markdown(_passed_report(), locale="zh-CN")
        assert "检查" in md or "报告" in md or "通过" in md

    def test_no_violations_no_details(self) -> None:
        """Report without violations omits details block."""
        md = format_markdown(_passed_report())
        assert "<details>" not in md
