"""Tests for Reporter formatting (R1, R2, Markdown)."""

from __future__ import annotations

from ac_guard.domain.models import CheckResult, StageOutcome, Violation
from ac_guard.reporter.formatting import (
    format_json,
    format_markdown,
    format_terminal,
)


def _passed_report() -> StageOutcome:
    """Create a passing report for testing."""
    return StageOutcome(
        stage="pre-commit",
        passed=True,
        results=[
            CheckResult(name="format", passed=True, duration_ms=23),
            CheckResult(name="naming", passed=True, duration_ms=15),
        ],
        duration_ms=38,
    )


def _failed_report() -> StageOutcome:
    """Create a failing report with violations."""
    return StageOutcome(
        stage="pre-push",
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


def _skipped_report() -> StageOutcome:
    """Create a report with skipped checks."""
    return StageOutcome(
        stage="pre-commit",
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
        """Passing report shows PASSED with emoji."""
        output = format_terminal(_passed_report())
        assert "✅ PASSED" in output
        assert "pre-commit" in output

    def test_failed_report(self) -> None:
        """Failing report shows FAILED with emoji and violation details."""
        output = format_terminal(_failed_report())
        assert "❌ FAILED" in output
        assert "src/main.py:10" in output
        assert "line too long" in output

    def test_skipped_checks(self) -> None:
        """Skipped checks show ⏭️ indicator."""
        output = format_terminal(_skipped_report())
        assert "⏭️" in output

    def test_violations_shown(self) -> None:
        """Violation file, line, code are displayed."""
        output = format_terminal(_failed_report())
        assert "E501" in output
        assert "src/util.py:22" in output

    def test_duration_shown(self) -> None:
        """Duration is displayed."""
        output = format_terminal(_passed_report())
        assert "38ms" in output

    def test_pass_fail_count(self) -> None:
        """Shows pass/fail summary count."""
        output = format_terminal(_failed_report())
        assert "1/2" in output

    def test_default_locale_uses_english_labels(self) -> None:
        """Default locale uses English labels with emojis."""
        output = format_terminal(_passed_report())
        assert "🤖 Stage: pre-commit — ✅ PASSED" in output
        assert "2/2 checks passed, 0 failed" in output
        assert "Total time" in output
        assert "📋 Checklist:" in output
        assert "📊 Results:" in output

    def test_zh_cn_locale_localizes_headings(self) -> None:
        """zh-CN localizes stage / summary / total_time labels and status."""
        output = format_terminal(_passed_report(), locale="zh-CN")
        assert "🤖 阶段: pre-commit — ✅ 通过" in output
        assert "2/2 项检查通过, 0 项失败" in output
        assert "总耗时" in output
        # English labels must not leak into zh-CN output
        assert "PASSED" not in output
        assert "Stage:" not in output

    def test_zh_cn_locale_failure_heading(self) -> None:
        """zh-CN locale shows ❌ 失败 when the report fails."""
        output = format_terminal(_failed_report(), locale="zh-CN")
        assert "🤖 阶段: pre-push — ❌ 失败" in output
        assert "1/2 项检查通过, 1 项失败" in output

    def test_unknown_locale_falls_back_to_english(self) -> None:
        """Unknown locale behaves like the default English labels."""
        output = format_terminal(_passed_report(), locale="fr-FR")
        assert "🤖 Stage: pre-commit — ✅ PASSED" in output
        assert "2/2 checks passed, 0 failed" in output


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


class TestFormatJson:
    """format_json function tests."""

    def test_output_is_valid_json(self) -> None:
        import json

        output = format_json(_passed_report())
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_contains_stage_and_passed(self) -> None:
        import json

        data = json.loads(format_json(_passed_report()))
        assert data["stage"] == "pre-commit"
        assert data["passed"] is True

    def test_contains_results(self) -> None:
        import json

        data = json.loads(format_json(_passed_report()))
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0]["name"] == "format"

    def test_violations_serialized(self) -> None:
        import json

        data = json.loads(format_json(_failed_report()))
        failed_results = [r for r in data["results"] if not r["passed"]]
        assert len(failed_results) == 1
        violations = failed_results[0]["violations"]
        assert len(violations) == 2
        assert violations[0]["file"] == "src/main.py"
        assert violations[0]["line"] == 10

    def test_duration_included(self) -> None:
        import json

        data = json.loads(format_json(_passed_report()))
        assert data["duration_ms"] == 38
