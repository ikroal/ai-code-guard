"""Tests for ac_guard.domain.models — Value Objects.

Managed-block protocol operations live in
``tests/unit/test_domain/test_managed_block.py``.
"""

from __future__ import annotations

from ac_guard.domain import CheckResult, FileSpec, StageOutcome, Violation


class TestFileSpec:
    def test_basic_construction(self) -> None:
        spec = FileSpec(path="test.txt", content="hello")
        assert spec.path == "test.txt"
        assert spec.content == "hello"
        assert spec.executable is False

    def test_executable_flag(self) -> None:
        spec = FileSpec(path="script.sh", content="#!/bin/bash", executable=True)
        assert spec.executable is True

    def test_all_fields(self) -> None:
        spec = FileSpec(
            path=".claude/hooks/interceptor.py",
            content="#!/usr/bin/env python",
            executable=True,
        )
        assert spec.path == ".claude/hooks/interceptor.py"
        assert spec.content == "#!/usr/bin/env python"
        assert spec.executable is True


class TestValueObjectExports:
    """Value Objects are exported at the package level."""

    def test_domain_package_exports(self) -> None:
        # Importability sanity check — the public surface is validated by
        # TestPackageApi below, this just ensures the re-exports resolve.
        from ac_guard.domain import (  # noqa: F401
            CheckResult,
            FileSpec,
            StageOutcome,
            Violation,
        )

    def test_models_module_all(self) -> None:
        import ac_guard.domain.models as models

        assert set(models.__all__) == {
            "CheckResult",
            "FileSpec",
            "StageOutcome",
            "Violation",
        }


class TestPackageApi:
    """Domain package exposes VOs + Domain Service sub-modules."""

    def test_domain_all(self) -> None:
        import ac_guard.domain as domain

        assert set(domain.__all__) == {
            "CheckResult",
            "FileSpec",
            "StageOutcome",
            "Violation",
            "languages",
            "managed_block",
            "stages",
        }

    def test_no_marker_leakage_on_domain(self) -> None:
        """Raw marker constants must not be accessible on ``ac_guard.domain``."""
        import ac_guard.domain as domain

        for name in (
            "MARKER_BEGIN",
            "MARKER_END",
            "MARKER_BEGIN_HASH",
            "MARKER_END_HASH",
            "markers_for",
            "wrap_with_markers",
        ):
            assert not hasattr(domain, name), (
                f"Unexpected marker-protocol leak on ac_guard.domain: {name}"
            )


class TestViolation:
    def test_defaults(self) -> None:
        v = Violation(file="x.py")
        assert v.file == "x.py"
        assert v.line is None
        assert v.severity == "error"
        assert v.code == ""
        assert v.message == ""
        assert v.source == ""


class TestCheckResult:
    def test_defaults(self) -> None:
        r = CheckResult(name="x", passed=True)
        assert r.name == "x"
        assert r.passed is True
        assert r.violations == []
        assert r.duration_ms == 0
        assert r.output == ""
        assert r.skipped is False


class TestStageOutcome:
    def test_defaults(self) -> None:
        s = StageOutcome(stage="pre-commit", passed=True)
        assert s.stage == "pre-commit"
        assert s.passed is True
        assert s.results == []
        assert s.duration_ms == 0
