"""Tests for Checker data models."""

from __future__ import annotations

from ac_guard.checker.models import CheckResult, StageOutcome, Violation


class TestViolation:
    """Tests for Violation dataclass."""

    def test_basic_construction(self) -> None:
        """Violation with required field only."""
        v = Violation(file="main.py")
        assert v.file == "main.py"
        assert v.line is None
        assert v.severity == "error"

    def test_full_construction(self) -> None:
        """Violation with all fields."""
        v = Violation(
            file="main.py",
            line=10,
            column=5,
            severity="warning",
            code="E501",
            message="line too long",
            source="ruff",
        )
        assert v.line == 10
        assert v.code == "E501"


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_passed_result(self) -> None:
        """Passing check result."""
        r = CheckResult(name="format", passed=True)
        assert r.passed is True
        assert r.violations == []
        assert r.skipped is False

    def test_failed_result(self) -> None:
        """Failed check result with violations."""
        r = CheckResult(
            name="lint",
            passed=False,
            violations=[Violation(file="a.py", message="err")],
        )
        assert r.passed is False
        assert len(r.violations) == 1

    def test_skipped_result(self) -> None:
        """Skipped check result."""
        r = CheckResult(name="build", passed=True, skipped=True)
        assert r.skipped is True


class TestStageOutcome:
    """Tests for StageOutcome dataclass."""

    def test_all_passed(self) -> None:
        """Report with all checks passing."""
        report = StageOutcome(
            stage="pre-commit",
            passed=True,
            results=[
                CheckResult(name="format", passed=True),
                CheckResult(name="naming", passed=True),
            ],
        )
        assert report.passed is True
        assert len(report.results) == 2

    def test_any_failed(self) -> None:
        """Report with a failing check."""
        report = StageOutcome(
            stage="pre-push",
            passed=False,
            results=[
                CheckResult(name="lint", passed=True),
                CheckResult(name="test", passed=False),
            ],
        )
        assert report.passed is False

    def test_empty_results(self) -> None:
        """Report with no results."""
        report = StageOutcome(stage="pre-commit", passed=True)
        assert report.results == []
