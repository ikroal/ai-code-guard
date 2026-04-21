"""Tests for Checker core orchestration (K2-K6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ac_guard.checker.core import (
    StageOptions,
    _filter_files_by_type,
    get_changed_files,
    run_build,
    run_check,
    run_stage,
)
from ac_guard.config.models import CheckItem, CodeConfig, StageBucket


class TestGetChangedFiles:
    """Tests for get_changed_files (K2)."""

    def test_commit_stage_command(self, tmp_path: Path) -> None:
        """Commit stage uses git diff --cached."""
        with patch("ac_guard.checker.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "a.py\nb.py\n"
            files = get_changed_files("pre-commit", tmp_path)
            assert files == ["a.py", "b.py"]
            cmd = mock_run.call_args[0][0]
            assert "--cached" in cmd

    def test_push_stage_command(self, tmp_path: Path) -> None:
        """Push stage uses git diff origin/main..HEAD."""
        with patch("ac_guard.checker.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "c.py\n"
            files = get_changed_files("pre-push", tmp_path)
            assert files == ["c.py"]
            cmd = mock_run.call_args[0][0]
            assert "origin/main..HEAD" in cmd

    def test_empty_output(self, tmp_path: Path) -> None:
        """Empty git output returns empty list."""
        with patch("ac_guard.checker.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            files = get_changed_files("pre-commit", tmp_path)
            assert files == []

    def test_git_error_returns_empty(self, tmp_path: Path) -> None:
        """Git error returns empty list."""
        with patch("ac_guard.checker.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            files = get_changed_files("pre-commit", tmp_path)
            assert files == []


class TestRunCheck:
    """Tests for run_check (K4)."""

    def test_successful_command(self, tmp_path: Path) -> None:
        """Successful command returns passed=True."""
        check = CheckItem(command="echo ok", timeout=10)
        result = run_check("echo-test", check, [], tmp_path)
        assert result.passed is True
        assert result.name == "echo-test"

    def test_failing_command(self, tmp_path: Path) -> None:
        """Failing command returns passed=False."""
        check = CheckItem(command="exit 1", timeout=10)
        result = run_check("fail-test", check, [], tmp_path)
        assert result.passed is False

    def test_timeout(self, tmp_path: Path) -> None:
        """Command timeout returns passed=False."""
        check = CheckItem(command="sleep 10", timeout=1)
        result = run_check("timeout-test", check, [], tmp_path)
        assert result.passed is False
        assert "Timed out" in result.output

    def test_disabled_check_skipped(self, tmp_path: Path) -> None:
        """Disabled check is skipped."""
        check = CheckItem(command="exit 1", enabled=False)
        result = run_check("disabled", check, [], tmp_path)
        assert result.passed is True
        assert result.skipped is True

    def test_no_matching_files_skipped(self, tmp_path: Path) -> None:
        """Check with types filter and no matching files is skipped."""
        check = CheckItem(command="ruff check", types=["python"])
        result = run_check("ruff", check, ["main.js"], tmp_path)
        assert result.passed is True
        assert result.skipped is True

    def test_pass_filenames(self, tmp_path: Path) -> None:
        """Files are appended when pass_filenames is True."""
        check = CheckItem(command="echo", types=["python"])
        result = run_check("echo", check, ["a.py", "b.py"], tmp_path)
        assert result.passed is True
        assert "a.py" in result.output


class TestRunBuild:
    """Tests for run_build (K5)."""

    def test_successful_build(self, tmp_path: Path) -> None:
        """Successful build returns passed=True."""
        result = run_build("echo build-ok", tmp_path)
        assert result.passed is True
        assert result.name == "build"

    def test_failing_build(self, tmp_path: Path) -> None:
        """Failing build returns passed=False."""
        result = run_build("exit 1", tmp_path)
        assert result.passed is False


class TestFilterFilesByType:
    """Tests for _filter_files_by_type helper."""

    def test_python_filter(self) -> None:
        """Python type filter matches .py files."""
        files = ["a.py", "b.js", "c.py"]
        assert _filter_files_by_type(files, ["python"]) == ["a.py", "c.py"]

    def test_no_filter(self) -> None:
        """None types returns all files."""
        files = ["a.py", "b.js"]
        assert _filter_files_by_type(files, None) == files

    def test_multiple_types(self) -> None:
        """Multiple type filters combined."""
        files = ["a.py", "b.ts", "c.go", "d.txt"]
        result = _filter_files_by_type(files, ["python", "typescript"])
        assert result == ["a.py", "b.ts"]


class TestRunStage:
    """Tests for run_stage orchestration (K6)."""

    def test_commit_stage_runs_checks(self, tmp_path: Path) -> None:
        """pre-commit stage runs format + custom checks."""
        config = CodeConfig(pre_commit=StageBucket(format=True))
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            report = run_stage("pre-commit", config, tmp_path)
        assert report.stage == "pre-commit"
        # Format and naming are pre-commit hooks — skipped with no files
        assert report.passed is True

    def test_commit_stage_with_custom_checks(self, tmp_path: Path) -> None:
        """Commit stage runs custom checks."""
        config = CodeConfig(
            pre_commit=StageBucket(
                format=False,
                checks={"echo": CheckItem(command="echo ok")},
            ),
        )
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            report = run_stage("pre-commit", config, tmp_path)
        assert report.passed is True
        assert any(r.name == "echo" for r in report.results)

    def test_push_stage_fail_fast(self, tmp_path: Path) -> None:
        """Push stage fails fast if commit stage fails."""
        config = CodeConfig(
            pre_commit=StageBucket(
                checks={"fail": CheckItem(command="exit 1")},
            ),
        )
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            report = run_stage("pre-push", config, tmp_path)
        assert report.stage == "pre-push"
        assert report.passed is False

    def test_push_stage_with_build(self, tmp_path: Path) -> None:
        """Push stage runs build command."""
        config = CodeConfig(
            pre_commit=StageBucket(format=False), pre_push=StageBucket(lint=False)
        )
        with patch("ac_guard.checker.core.get_changed_files", return_value=[]):
            report = run_stage(
                "pre-push",
                config,
                tmp_path,
                options=StageOptions(build_command="echo build"),
            )
        assert report.passed is True
        assert any(r.name == "build" for r in report.results)

    def test_format_iterates_per_language(self, tmp_path: Path) -> None:
        """commit_format=True emits one pre-commit call per configured language."""
        config = CodeConfig(pre_commit=StageBucket(format=True))
        with patch("ac_guard.checker.core.run_precommit") as mock_run:
            mock_run.return_value.passed = True
            mock_run.return_value.name = "stub"
            mock_run.return_value.duration_ms = 0
            mock_run.return_value.skipped = False
            mock_run.return_value.violations = []
            mock_run.return_value.output = ""
            run_stage(
                "pre-commit",
                config,
                tmp_path,
                options=StageOptions(
                    files=["a.py"],
                    languages=["python", "typescript"],
                ),
            )
        hook_ids = [call.args[0] for call in mock_run.call_args_list]
        assert "format-python" in hook_ids
        assert "format-typescript" in hook_ids

    def test_lint_iterates_per_language(self, tmp_path: Path) -> None:
        """push_lint=True emits one pre-commit call per configured language."""
        config = CodeConfig(
            pre_commit=StageBucket(format=False), pre_push=StageBucket(lint=True)
        )
        with patch("ac_guard.checker.core.run_precommit") as mock_run:
            mock_run.return_value.passed = True
            mock_run.return_value.name = "stub"
            mock_run.return_value.duration_ms = 0
            mock_run.return_value.skipped = False
            mock_run.return_value.violations = []
            mock_run.return_value.output = ""
            with patch(
                "ac_guard.checker.core.get_changed_files", return_value=["a.py"]
            ):
                run_stage(
                    "pre-push",
                    config,
                    tmp_path,
                    options=StageOptions(languages=["python", "typescript"]),
                )
        hook_ids = [call.args[0] for call in mock_run.call_args_list]
        assert "lint-python" in hook_ids
        assert "lint-typescript" in hook_ids

    # D8: ``commit_naming`` flag removed in schema v2 (#123). Shim in
    # CodeConfig always returns False, so the checker's naming branch
    # is now unreachable. The dedicated "naming returns skipped" test
    # is obsolete; ruff N-rules (via ``lint: true``) replaced it.

    def test_no_languages_skips_format_and_lint(self, tmp_path: Path) -> None:
        """Empty languages list silently skips format/lint shortcuts."""
        config = CodeConfig(
            pre_commit=StageBucket(format=True), pre_push=StageBucket(lint=True)
        )
        with (
            patch("ac_guard.checker.core.run_precommit") as mock_run,
            patch("ac_guard.checker.core.get_changed_files", return_value=["a.py"]),
        ):
            run_stage("pre-push", config, tmp_path, options=StageOptions(languages=[]))
        mock_run.assert_not_called()

    def test_push_build_failure_skips_lint_and_checks(self, tmp_path: Path) -> None:
        """#77: a failing build must mark lint + push.checks as skipped."""
        from ac_guard.checker.models import CheckResult

        config = CodeConfig(
            pre_commit=StageBucket(format=False),
            pre_push=StageBucket(
                lint=True,
                checks={"custom": CheckItem(command="echo should-not-run")},
            ),
        )
        failing_build = CheckResult(
            name="build", passed=False, duration_ms=10, output="build broke"
        )
        with (
            patch(
                "ac_guard.checker.core.run_build", return_value=failing_build
            ) as build_mock,
            patch("ac_guard.checker.core.run_precommit") as precommit_mock,
            patch("ac_guard.checker.core.run_check") as check_mock,
            patch("ac_guard.checker.core.get_changed_files", return_value=["a.py"]),
        ):
            report = run_stage(
                "pre-push",
                config,
                tmp_path,
                options=StageOptions(
                    build_command="make build",
                    languages=["python"],
                ),
            )

        # Build ran once, downstream checkers never invoked
        assert build_mock.call_count == 1
        precommit_mock.assert_not_called()
        check_mock.assert_not_called()

        # Report is failed because build failed
        assert report.passed is False
        names = {r.name: r for r in report.results}
        assert names["build"].passed is False
        assert names["pre-commit:lint-python"].skipped is True
        assert "build failed" in names["pre-commit:lint-python"].output.lower()
        assert names["custom"].skipped is True
        assert "build failed" in names["custom"].output.lower()

    def test_push_build_success_runs_downstream(self, tmp_path: Path) -> None:
        """Build success preserves the existing downstream execution path."""
        from ac_guard.checker.models import CheckResult

        config = CodeConfig(
            pre_commit=StageBucket(format=False),
            pre_push=StageBucket(
                lint=True,
                checks={"custom": CheckItem(command="echo ok")},
            ),
        )
        passing_build = CheckResult(name="build", passed=True, duration_ms=10)
        with (
            patch("ac_guard.checker.core.run_build", return_value=passing_build),
            patch("ac_guard.checker.core.run_precommit") as precommit_mock,
            patch("ac_guard.checker.core.run_check") as check_mock,
            patch("ac_guard.checker.core.get_changed_files", return_value=["a.py"]),
        ):
            precommit_mock.return_value = CheckResult(
                name="pre-commit:lint-python", passed=True, duration_ms=1
            )
            check_mock.return_value = CheckResult(
                name="custom", passed=True, duration_ms=1
            )
            run_stage(
                "pre-push",
                config,
                tmp_path,
                options=StageOptions(
                    build_command="make build",
                    languages=["python"],
                ),
            )
        precommit_mock.assert_called()
        check_mock.assert_called()
