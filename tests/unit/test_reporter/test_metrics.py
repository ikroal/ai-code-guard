"""Tests for reporter.metrics — metrics extraction and enrichment."""

from __future__ import annotations

from unittest.mock import patch

from ac_guard.domain.models import CheckMetrics, CheckResult, StageOutcome
from ac_guard.reporter.metrics import (
    build_checklist,
    enrich_outcome,
)


class TestPytestParser:
    """Parse pytest output for test counts and coverage."""

    def test_basic_summary(self) -> None:
        output = "129 passed in 0.41s"
        from ac_guard.reporter.metrics import _parse_pytest

        result = _parse_pytest("pytest", output)
        assert result is not None
        assert result.tests_total == 129
        assert result.tests_passed == 129
        assert result.tests_failed == 0
        assert result.tests_skipped == 0
        assert result.coverage_pct is None

    def test_summary_with_failures(self) -> None:
        output = "128 passed, 1 failed, 2 skipped in 1.2s"
        from ac_guard.reporter.metrics import _parse_pytest

        result = _parse_pytest("pytest", output)
        assert result is not None
        assert result.tests_total == 131
        assert result.tests_passed == 128
        assert result.tests_failed == 1
        assert result.tests_skipped == 2

    def test_with_coverage(self) -> None:
        output = (
            "129 passed in 0.41s\n"
            "---------- coverage: platform darwin ----------\n"
            "Name                     Stmts   Miss  Cover\n"
            "TOTAL                     1234    185    85%\n"
        )
        from ac_guard.reporter.metrics import _parse_pytest

        result = _parse_pytest("pytest", output)
        assert result is not None
        assert result.tests_total == 129
        assert result.coverage_pct == 85.0

    def test_no_match(self) -> None:
        from ac_guard.reporter.metrics import _parse_pytest

        assert _parse_pytest("pytest", "some random output") is None


class TestInterrogateParser:
    """Parse interrogate output for docstring coverage."""

    def test_passed_result(self) -> None:
        output = "RESULT: PASSED (100.0%)"
        from ac_guard.reporter.metrics import _parse_interrogate

        result = _parse_interrogate("interrogate", output)
        assert result is not None
        assert result.docstring_pct == 100.0

    def test_partial_result(self) -> None:
        output = "RESULT: FAILED (53.6%)"
        from ac_guard.reporter.metrics import _parse_interrogate

        result = _parse_interrogate("interrogate", output)
        assert result is not None
        assert result.docstring_pct == 53.6

    def test_no_match(self) -> None:
        from ac_guard.reporter.metrics import _parse_interrogate

        assert _parse_interrogate("interrogate", "no results here") is None


class TestRuffParser:
    """Parse ruff output for lint issue count."""

    def test_errors_found(self) -> None:
        output = "Found 3 errors."
        from ac_guard.reporter.metrics import _parse_ruff

        result = _parse_ruff("ruff", output)
        assert result is not None
        assert result.static_analysis_issues == 3

    def test_no_errors(self) -> None:
        output = "All checks passed!"
        from ac_guard.reporter.metrics import _parse_ruff

        assert _parse_ruff("ruff", output) is None


class TestBanditParser:
    """Parse bandit output for security issue count."""

    def test_issues_found(self) -> None:
        output = (
            "Total issues (by severity):\n"
            "        High: 1\n"
            "        Medium: 0\n"
            "        Low: 2\n"
        )
        from ac_guard.reporter.metrics import _parse_bandit

        result = _parse_bandit("bandit", output)
        assert result is not None
        assert result.static_analysis_issues == 3

    def test_no_issues(self) -> None:
        output = (
            "Total issues (by severity):\n"
            "        High: 0\n"
            "        Medium: 0\n"
            "        Low: 0\n"
        )
        from ac_guard.reporter.metrics import _parse_bandit

        assert _parse_bandit("bandit", output) is None


class TestEnrichOutcome:
    """enrich_outcome() populates metrics on CheckResult."""

    def test_enriches_pytest_output(self) -> None:
        outcome = StageOutcome(
            stage="pre-push",
            passed=True,
            results=[
                CheckResult(
                    name="pytest",
                    passed=True,
                    output="129 passed in 0.41s",
                ),
            ],
        )
        enriched = enrich_outcome(outcome)
        assert enriched.results[0].metrics is not None
        assert enriched.results[0].metrics.tests_total == 129

    def test_skips_already_enriched(self) -> None:
        existing = CheckMetrics(tests_total=999)
        outcome = StageOutcome(
            stage="pre-push",
            passed=True,
            results=[
                CheckResult(
                    name="pytest",
                    passed=True,
                    output="129 passed in 0.41s",
                    metrics=existing,
                ),
            ],
        )
        enriched = enrich_outcome(outcome)
        assert enriched.results[0].metrics.tests_total == 999  # Not overwritten

    def test_sets_generated_at(self) -> None:
        outcome = StageOutcome(stage="pre-push", passed=True)
        enriched = enrich_outcome(outcome)
        assert enriched.generated_at != ""

    def test_detects_guard_changes(self) -> None:
        outcome = StageOutcome(stage="pre-push", passed=True)
        with patch(
            "ac_guard.reporter.metrics._detect_guard_changes",
            return_value=["guard.yaml"],
        ):
            enriched = enrich_outcome(outcome)
        assert enriched.guard_files_changed == ["guard.yaml"]


class TestBuildChecklist:
    """build_checklist() maps check results to checklist items."""

    def test_format_and_lint(self) -> None:
        outcome = StageOutcome(
            stage="pre-commit",
            passed=True,
            results=[
                CheckResult(name="format-python", passed=True),
                CheckResult(name="lint-python", passed=True),
            ],
        )
        items = build_checklist(outcome)
        labels = [i.label for i in items]
        assert "Code formatting" in labels
        assert "Linting" in labels

    def test_with_metrics(self) -> None:
        outcome = StageOutcome(
            stage="pre-push",
            passed=True,
            results=[
                CheckResult(
                    name="pytest",
                    passed=True,
                    metrics=CheckMetrics(tests_total=129, tests_passed=129),
                ),
            ],
        )
        items = build_checklist(outcome)
        assert len(items) == 1
        assert items[0].label == "Tests"
        assert items[0].detail == "129/129"
        assert items[0].status == "pass"

    def test_skipped_checks_excluded(self) -> None:
        outcome = StageOutcome(
            stage="pre-push",
            passed=True,
            results=[
                CheckResult(name="pytest", passed=True, skipped=True),
            ],
        )
        items = build_checklist(outcome)
        assert len(items) == 0

    def test_unknown_check_excluded(self) -> None:
        outcome = StageOutcome(
            stage="pre-push",
            passed=True,
            results=[
                CheckResult(name="unknown-tool", passed=True),
            ],
        )
        items = build_checklist(outcome)
        assert len(items) == 0
