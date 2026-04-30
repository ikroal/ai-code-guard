"""Tests for code_gate orchestration: gate_stage / gate_check + private helpers."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from ac_guard.code_gate.core import (
    GateOptions,
    _delegate_managed_stage,
    _filter_files_by_type,
    _get_changed_files,
    _run_build,
    _run_check_item,
    _run_command,
    gate_check,
    gate_stage,
    is_modeled_stage,
)
from ac_guard.config.models import CheckItem, CodeConfig, StageBucket
from ac_guard.domain.models import CheckResult


class TestGetChangedFiles:
    """File collection via git diff."""

    def test_commit_stage_command(self, tmp_path: Path) -> None:
        """Commit stage uses git diff --cached."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "a.py\nb.py\n"
            files = _get_changed_files("pre-commit", tmp_path)
            assert files == ["a.py", "b.py"]
            cmd = mock_run.call_args[0][0]
            assert "--cached" in cmd

    def test_push_stage_command(self, tmp_path: Path) -> None:
        """Push stage uses git diff origin/main..HEAD."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "c.py\n"
            files = _get_changed_files("pre-push", tmp_path)
            assert files == ["c.py"]
            cmd = mock_run.call_args[0][0]
            assert "origin/main..HEAD" in cmd

    def test_empty_output(self, tmp_path: Path) -> None:
        """Empty git output returns empty list."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            files = _get_changed_files("pre-commit", tmp_path)
            assert files == []

    def test_git_error_returns_empty(self, tmp_path: Path) -> None:
        """Git error returns empty list."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            files = _get_changed_files("pre-commit", tmp_path)
            assert files == []


class TestRunCheckItem:
    """Adapter from CheckItem to _run_command."""

    def test_successful_command(self, tmp_path: Path) -> None:
        """Successful command returns passed=True."""
        check = CheckItem(command="echo ok", timeout=10)
        result = _run_check_item("echo-test", check, [], tmp_path)
        assert result.passed is True
        assert result.name == "echo-test"

    def test_failing_command(self, tmp_path: Path) -> None:
        """Failing command returns passed=False."""
        check = CheckItem(command="exit 1", timeout=10)
        result = _run_check_item("fail-test", check, [], tmp_path)
        assert result.passed is False

    def test_timeout(self, tmp_path: Path) -> None:
        """Command timeout returns passed=False."""
        check = CheckItem(command="sleep 10", timeout=1)
        result = _run_check_item("timeout-test", check, [], tmp_path)
        assert result.passed is False
        assert "Timed out" in result.output

    def test_disabled_check_skipped(self, tmp_path: Path) -> None:
        """Disabled check is skipped."""
        check = CheckItem(command="exit 1", enabled=False)
        result = _run_check_item("disabled", check, [], tmp_path)
        assert result.passed is True
        assert result.skipped is True

    def test_no_matching_files_skipped(self, tmp_path: Path) -> None:
        """Check with types filter and no matching files is skipped."""
        check = CheckItem(command="ruff check", types=["python"])
        result = _run_check_item("ruff", check, ["main.js"], tmp_path)
        assert result.passed is True
        assert result.skipped is True

    def test_pass_filenames(self, tmp_path: Path) -> None:
        """Files are appended when pass_filenames is True."""
        check = CheckItem(command="echo", types=["python"])
        result = _run_check_item("echo", check, ["a.py", "b.py"], tmp_path)
        assert result.passed is True
        assert "a.py" in result.output


class TestRunBuild:
    """Build adapter (literal command + 600s timeout + fixed name)."""

    def test_successful_build(self, tmp_path: Path) -> None:
        result = _run_build("echo build-ok", tmp_path)
        assert result.passed is True
        assert result.name == "build"

    def test_failing_build(self, tmp_path: Path) -> None:
        result = _run_build("exit 1", tmp_path)
        assert result.passed is False


class TestRunCommand:
    """Pure literal-command runner (the shared subprocess backend)."""

    def test_naming_passthrough(self, tmp_path: Path) -> None:
        """The ``name`` argument is preserved on the result."""
        result = _run_command("custom-name", "echo ok", tmp_path, timeout=5)
        assert result.name == "custom-name"
        assert result.passed is True

    def test_failing_command_marks_failed(self, tmp_path: Path) -> None:
        result = _run_command("fail", "exit 3", tmp_path, timeout=5)
        assert result.passed is False


class TestRunCheckItemSubstitution:
    """File-list substitution / type filtering live in _run_check_item."""

    def test_files_substituted_when_placeholder_present(self, tmp_path: Path) -> None:
        check = CheckItem(
            command="echo prefix {files} suffix",
            types=["python"],
            pass_filenames=True,
        )
        result = _run_check_item("echo-sub", check, ["a.py"], tmp_path)
        assert "prefix a.py suffix" in result.output


class TestFilterFilesByType:
    def test_python_filter(self) -> None:
        files = ["a.py", "b.js", "c.py"]
        assert _filter_files_by_type(files, ["python"]) == ["a.py", "c.py"]

    def test_no_filter(self) -> None:
        files = ["a.py", "b.js"]
        assert _filter_files_by_type(files, None) == files

    def test_multiple_types(self) -> None:
        files = ["a.py", "b.ts", "c.go", "d.txt"]
        assert _filter_files_by_type(files, ["python", "typescript"]) == [
            "a.py",
            "b.ts",
        ]


class TestIsModeledStage:
    def test_modeled(self) -> None:
        assert is_modeled_stage("pre-commit") is True
        assert is_modeled_stage("pre-push") is True

    def test_not_modeled(self) -> None:
        assert is_modeled_stage("commit-msg") is False
        assert is_modeled_stage("pre-merge-commit") is False
        assert is_modeled_stage("pre-rebase") is False

    def test_unknown(self) -> None:
        """Unknown stages are not modeled."""
        assert is_modeled_stage("post-commit") is False


class TestGateStage:
    """Bucket-aware orchestration via gate_stage."""

    def test_commit_stage_runs_checks(self, tmp_path: Path) -> None:
        config = CodeConfig(pre_commit=StageBucket(format=True))
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            outcome = gate_stage("pre-commit", config, tmp_path)
        assert outcome.stage == "pre-commit"
        assert outcome.passed is True

    def test_commit_stage_with_custom_checks(self, tmp_path: Path) -> None:
        config = CodeConfig(
            pre_commit=StageBucket(
                format=False,
                checks={"echo": CheckItem(command="echo ok")},
            ),
        )
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            outcome = gate_stage("pre-commit", config, tmp_path)
        assert outcome.passed is True
        assert any(r.name == "echo" for r in outcome.results)

    def test_push_stage_fail_fast(self, tmp_path: Path) -> None:
        config = CodeConfig(
            pre_commit=StageBucket(
                checks={"fail": CheckItem(command="exit 1")},
            ),
        )
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            outcome = gate_stage("pre-push", config, tmp_path)
        assert outcome.stage == "pre-push"
        assert outcome.passed is False

    def test_push_stage_with_build(self, tmp_path: Path) -> None:
        config = CodeConfig(
            pre_commit=StageBucket(format=False), pre_push=StageBucket(lint=False)
        )
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            outcome = gate_stage(
                "pre-push",
                config,
                tmp_path,
                options=GateOptions(build_command="echo build"),
            )
        assert outcome.passed is True
        assert any(r.name == "build" for r in outcome.results)

    def test_format_iterates_per_language(self, tmp_path: Path) -> None:
        config = CodeConfig(pre_commit=StageBucket(format=True))
        with patch("ac_guard.code_gate.core._run_managed_hook") as mock_hook:
            mock_hook.return_value = CheckResult(name="stub", passed=True)
            gate_stage(
                "pre-commit",
                config,
                tmp_path,
                options=GateOptions(
                    files=["a.py"],
                    languages=["python", "typescript"],
                ),
            )
        hook_ids = [call.args[0] for call in mock_hook.call_args_list]
        assert "format-python" in hook_ids
        assert "format-typescript" in hook_ids

    def test_lint_iterates_per_language(self, tmp_path: Path) -> None:
        config = CodeConfig(
            pre_commit=StageBucket(format=False), pre_push=StageBucket(lint=True)
        )
        with (
            patch("ac_guard.code_gate.core._run_managed_hook") as mock_hook,
            patch("ac_guard.code_gate.core._get_changed_files", return_value=["a.py"]),
        ):
            mock_hook.return_value = CheckResult(name="stub", passed=True)
            gate_stage(
                "pre-push",
                config,
                tmp_path,
                options=GateOptions(languages=["python", "typescript"]),
            )
        hook_ids = [call.args[0] for call in mock_hook.call_args_list]
        assert "lint-python" in hook_ids
        assert "lint-typescript" in hook_ids

    def test_no_languages_skips_format_and_lint(self, tmp_path: Path) -> None:
        """Empty languages list silently skips format/lint shortcuts."""
        config = CodeConfig(
            pre_commit=StageBucket(format=True), pre_push=StageBucket(lint=True)
        )
        with (
            patch("ac_guard.code_gate.core._run_managed_hook") as mock_hook,
            patch("ac_guard.code_gate.core._get_changed_files", return_value=["a.py"]),
        ):
            gate_stage("pre-push", config, tmp_path, options=GateOptions(languages=[]))
        mock_hook.assert_not_called()

    def test_push_build_failure_skips_lint_and_checks(self, tmp_path: Path) -> None:
        """A failing build marks lint + push.checks as skipped."""
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
                "ac_guard.code_gate.core._run_build", return_value=failing_build
            ) as build_mock,
            patch("ac_guard.code_gate.core._run_managed_hook") as hook_mock,
            patch("ac_guard.code_gate.core._run_check_item") as check_mock,
            patch("ac_guard.code_gate.core._get_changed_files", return_value=["a.py"]),
        ):
            outcome = gate_stage(
                "pre-push",
                config,
                tmp_path,
                options=GateOptions(
                    build_command="make build",
                    languages=["python"],
                ),
            )

        assert build_mock.call_count == 1
        hook_mock.assert_not_called()
        check_mock.assert_not_called()

        assert outcome.passed is False
        names = {r.name: r for r in outcome.results}
        assert names["build"].passed is False
        assert names["pre-commit:lint-python"].skipped is True
        assert "build failed" in names["pre-commit:lint-python"].output.lower()
        assert names["custom"].skipped is True
        assert "build failed" in names["custom"].output.lower()

    def test_push_build_success_runs_downstream(self, tmp_path: Path) -> None:
        """Build success preserves downstream execution."""
        config = CodeConfig(
            pre_commit=StageBucket(format=False),
            pre_push=StageBucket(
                lint=True,
                checks={"custom": CheckItem(command="echo ok")},
            ),
        )
        passing_build = CheckResult(name="build", passed=True, duration_ms=10)
        with (
            patch("ac_guard.code_gate.core._run_build", return_value=passing_build),
            patch("ac_guard.code_gate.core._run_managed_hook") as hook_mock,
            patch("ac_guard.code_gate.core._run_check_item") as check_mock,
            patch("ac_guard.code_gate.core._get_changed_files", return_value=["a.py"]),
        ):
            hook_mock.return_value = CheckResult(
                name="pre-commit:lint-python", passed=True, duration_ms=1
            )
            check_mock.return_value = CheckResult(
                name="custom", passed=True, duration_ms=1
            )
            gate_stage(
                "pre-push",
                config,
                tmp_path,
                options=GateOptions(
                    build_command="make build",
                    languages=["python"],
                ),
            )
        hook_mock.assert_called()
        check_mock.assert_called()

    def test_unknown_stage_raises_value_error(self, tmp_path: Path) -> None:
        """Stage outside the 5 gating moments raises ValueError."""
        with pytest.raises(ValueError, match="Unknown stage"):
            gate_stage("post-commit", CodeConfig(), tmp_path)

    def test_non_modeled_stage_delegates(self, tmp_path: Path) -> None:
        """Non-modeled stages route through _delegate_managed_stage."""
        with patch(
            "ac_guard.code_gate.core._delegate_managed_stage", return_value=0
        ) as delegate_mock:
            outcome = gate_stage("commit-msg", CodeConfig(), tmp_path)
        assert delegate_mock.call_count == 1
        assert outcome.stage == "commit-msg"
        assert outcome.passed is True
        assert outcome.results == []

    def test_non_modeled_stage_failed_delegation(self, tmp_path: Path) -> None:
        """Non-zero delegation rc maps to passed=False."""
        with patch("ac_guard.code_gate.core._delegate_managed_stage", return_value=42):
            outcome = gate_stage("pre-rebase", CodeConfig(), tmp_path)
        assert outcome.passed is False

    def test_non_modeled_stage_argv_forwarded(self, tmp_path: Path) -> None:
        """commit-msg argv is forwarded through GateOptions to delegation."""
        with patch(
            "ac_guard.code_gate.core._delegate_managed_stage", return_value=0
        ) as delegate_mock:
            gate_stage(
                "commit-msg",
                CodeConfig(),
                tmp_path,
                options=GateOptions(argv=["/tmp/msg-file"]),
            )
        assert delegate_mock.call_args.kwargs["argv"] == ["/tmp/msg-file"]


class TestGateCheck:
    """Single named-check resolution and execution."""

    def test_format_expands_per_language(self, tmp_path: Path) -> None:
        with patch("ac_guard.code_gate.core._run_managed_hook") as mock_hook:
            mock_hook.return_value = CheckResult(name="stub", passed=True)
            gate_check(
                "format",
                CodeConfig(),
                tmp_path,
                options=GateOptions(
                    files=["a.py"],
                    languages=["python", "typescript"],
                ),
            )
        hook_ids = [call.args[0] for call in mock_hook.call_args_list]
        assert hook_ids == ["format-python", "format-typescript"]

    def test_lint_expands_per_language(self, tmp_path: Path) -> None:
        with patch("ac_guard.code_gate.core._run_managed_hook") as mock_hook:
            mock_hook.return_value = CheckResult(name="stub", passed=True)
            gate_check(
                "lint",
                CodeConfig(),
                tmp_path,
                options=GateOptions(
                    files=["a.py"],
                    languages=["python"],
                ),
            )
        hook_ids = [call.args[0] for call in mock_hook.call_args_list]
        assert hook_ids == ["lint-python"]

    def test_format_with_no_languages_skipped(self, tmp_path: Path) -> None:
        outcome = gate_check(
            "format",
            CodeConfig(),
            tmp_path,
            options=GateOptions(files=["a.py"], languages=[]),
        )
        assert outcome.passed is True
        assert len(outcome.results) == 1
        assert outcome.results[0].skipped is True

    def test_naming_returns_skipped_placeholder(self, tmp_path: Path) -> None:
        outcome = gate_check(
            "naming",
            CodeConfig(),
            tmp_path,
            options=GateOptions(files=["a.py"]),
        )
        assert outcome.passed is True
        assert outcome.results[0].skipped is True
        assert "Naming check is not yet implemented" in outcome.results[0].output

    def test_custom_check_resolved_across_buckets(self, tmp_path: Path) -> None:
        """A custom check from any bucket is found by name."""
        config = CodeConfig(
            pre_push=StageBucket(checks={"mypy": CheckItem(command="echo ok")}),
        )
        outcome = gate_check(
            "mypy",
            config,
            tmp_path,
            options=GateOptions(files=[]),
        )
        assert outcome.passed is True
        assert outcome.results[0].name == "mypy"

    def test_unknown_check_raises_key_error_with_available(
        self, tmp_path: Path
    ) -> None:
        """KeyError message lists available check names for CLI rendering."""
        config = CodeConfig(
            pre_commit=StageBucket(checks={"echo": CheckItem(command="echo ok")}),
            pre_push=StageBucket(checks={"mypy": CheckItem(command="echo ok")}),
        )
        with pytest.raises(KeyError) as exc_info:
            gate_check(
                "nonexistent",
                config,
                tmp_path,
                options=GateOptions(files=[]),
            )
        message = exc_info.value.args[0]
        assert "nonexistent" in message
        assert "echo" in message
        assert "mypy" in message

    def test_outcome_stage_marker(self, tmp_path: Path) -> None:
        """The synthetic outcome.stage is ``ad-hoc:<name>``."""
        config = CodeConfig(
            pre_commit=StageBucket(checks={"echo": CheckItem(command="echo ok")}),
        )
        outcome = gate_check("echo", config, tmp_path, options=GateOptions(files=[]))
        assert outcome.stage == "ad-hoc:echo"


class TestDelegateManagedStage:
    """Pre-commit framework delegation for non-modeled stages.

    Covers what the previous CLI ``_run_precommit_stage`` helper did
    before it was relocated into ``code_gate.core``.
    """

    def test_returns_subprocess_returncode(self, tmp_path: Path) -> None:
        """Exit code from the pre-commit subprocess propagates verbatim."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=42)
            assert _delegate_managed_stage("pre-rebase", tmp_path) == 42

    def test_invokes_pre_commit_with_hook_stage(self, tmp_path: Path) -> None:
        """Command starts with `pre-commit run --hook-stage <stage>`."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _delegate_managed_stage("pre-merge-commit", tmp_path)
            cmd = mock_run.call_args.args[0]
            assert cmd[:4] == [
                "pre-commit",
                "run",
                "--hook-stage",
                "pre-merge-commit",
            ]

    def test_commit_msg_argv_forwarded(self, tmp_path: Path) -> None:
        """commit-msg with argv forwards msg file via --commit-msg-filename."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _delegate_managed_stage("commit-msg", tmp_path, argv=["/tmp/msg-file"])
            cmd = mock_run.call_args.args[0]
            assert "--commit-msg-filename" in cmd
            assert "/tmp/msg-file" in cmd
            assert "--all-files" not in cmd

    def test_commit_msg_no_argv_falls_back_to_all_files(self, tmp_path: Path) -> None:
        """commit-msg without argv falls back to --all-files."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _delegate_managed_stage("commit-msg", tmp_path, argv=None)
            cmd = mock_run.call_args.args[0]
            assert "--all-files" in cmd
            assert "--commit-msg-filename" not in cmd

    def test_non_commit_msg_uses_all_files_even_with_argv(self, tmp_path: Path) -> None:
        """Non-commit-msg stages always use --all-files; argv is ignored."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _delegate_managed_stage("pre-rebase", tmp_path, argv=["arg1"])
            cmd = mock_run.call_args.args[0]
            assert "--all-files" in cmd
            assert "--commit-msg-filename" not in cmd

    def test_passes_cwd_and_check_false(self, tmp_path: Path) -> None:
        """project_root is forwarded as cwd; check=False so we own exit code."""
        with patch("ac_guard.code_gate.core.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess([], returncode=0)
            _delegate_managed_stage("pre-merge-commit", tmp_path)
            assert mock_run.call_args.kwargs["cwd"] == tmp_path
            assert mock_run.call_args.kwargs["check"] is False


class TestStageStrategies:
    """White-box tests for the per-stage strategy classes.

    ``gate_stage`` / ``is_modeled_stage`` route to these strategies. The
    public-facing tests in ``TestGateStage`` / ``TestIsModeledStage``
    cover end-to-end behavior; here we exercise each strategy directly
    to pin down their contracts.
    """

    def test_commit_strategy_metadata(self) -> None:
        from ac_guard.code_gate.core import _CommitStrategy

        strategy = _CommitStrategy()
        assert strategy.stage == "pre-commit"
        assert strategy.is_modeled is True

    def test_commit_strategy_run_uses_pre_commit_bucket(self, tmp_path: Path) -> None:
        from ac_guard.code_gate.core import _CommitStrategy

        config = CodeConfig(
            pre_commit=StageBucket(checks={"echo": CheckItem(command="echo ok")}),
        )
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            outcome = _CommitStrategy().run(config, tmp_path, GateOptions())
        assert outcome.stage == "pre-commit"
        assert outcome.passed is True
        assert any(r.name == "echo" for r in outcome.results)

    def test_push_strategy_metadata(self) -> None:
        from ac_guard.code_gate.core import _CommitStrategy, _PushStrategy

        strategy = _PushStrategy(_CommitStrategy())
        assert strategy.stage == "pre-push"
        assert strategy.is_modeled is True

    def test_push_strategy_runs_commit_first_for_fail_fast(
        self, tmp_path: Path
    ) -> None:
        """Push strategy must call commit strategy first; fail short-circuits."""
        from ac_guard.code_gate.core import _CommitStrategy, _PushStrategy

        config = CodeConfig(
            pre_commit=StageBucket(
                checks={"fail": CheckItem(command="exit 1")},
            ),
        )
        with patch("ac_guard.code_gate.core._get_changed_files", return_value=[]):
            outcome = _PushStrategy(_CommitStrategy()).run(
                config, tmp_path, GateOptions()
            )
        assert outcome.stage == "pre-push"
        assert outcome.passed is False
        # Failed pre-commit results bubble up under the pre-push stage label
        assert any(r.name == "fail" for r in outcome.results)

    def test_push_strategy_runs_build_after_commit_passes(self, tmp_path: Path) -> None:
        from ac_guard.code_gate.core import _CommitStrategy, _PushStrategy

        config = CodeConfig(
            pre_commit=StageBucket(format=False),
            pre_push=StageBucket(lint=False),
        )
        with (
            patch("ac_guard.code_gate.core._get_changed_files", return_value=[]),
            patch(
                "ac_guard.code_gate.core._run_build",
                return_value=CheckResult(name="build", passed=True),
            ) as mock_build,
        ):
            outcome = _PushStrategy(_CommitStrategy()).run(
                config, tmp_path, GateOptions(build_command="echo build")
            )
        assert outcome.passed is True
        mock_build.assert_called_once()

    def test_delegated_strategy_metadata(self) -> None:
        from ac_guard.code_gate.core import _DelegatedStrategy

        strategy = _DelegatedStrategy("commit-msg")
        assert strategy.stage == "commit-msg"
        assert strategy.is_modeled is False

    def test_delegated_strategy_wraps_exit_code(self, tmp_path: Path) -> None:
        from ac_guard.code_gate.core import _DelegatedStrategy

        with patch("ac_guard.code_gate.core._delegate_managed_stage", return_value=0):
            outcome = _DelegatedStrategy("commit-msg").run(
                CodeConfig(), tmp_path, GateOptions()
            )
        assert outcome.passed is True
        assert outcome.results == []
        assert outcome.stage == "commit-msg"

    def test_delegated_strategy_failure_maps_to_passed_false(
        self, tmp_path: Path
    ) -> None:
        from ac_guard.code_gate.core import _DelegatedStrategy

        with patch("ac_guard.code_gate.core._delegate_managed_stage", return_value=42):
            outcome = _DelegatedStrategy("pre-rebase").run(
                CodeConfig(), tmp_path, GateOptions()
            )
        assert outcome.passed is False

    def test_delegated_strategy_forwards_argv(self, tmp_path: Path) -> None:
        from ac_guard.code_gate.core import _DelegatedStrategy

        with patch(
            "ac_guard.code_gate.core._delegate_managed_stage", return_value=0
        ) as mock_delegate:
            _DelegatedStrategy("commit-msg").run(
                CodeConfig(), tmp_path, GateOptions(argv=["/tmp/msg-file"])
            )
        assert mock_delegate.call_args.kwargs["argv"] == ["/tmp/msg-file"]


class TestStrategyRegistry:
    """The ``_STRATEGIES`` table backs ``gate_stage`` / ``is_modeled_stage``."""

    def test_all_five_gating_stages_registered(self) -> None:
        from ac_guard.code_gate.core import _STRATEGIES

        assert set(_STRATEGIES) == {
            "pre-commit",
            "pre-push",
            "commit-msg",
            "pre-merge-commit",
            "pre-rebase",
        }

    def test_get_strategy_returns_correct_type(self) -> None:
        from ac_guard.code_gate.core import (
            _CommitStrategy,
            _DelegatedStrategy,
            _get_strategy,
            _PushStrategy,
        )

        assert isinstance(_get_strategy("pre-commit"), _CommitStrategy)
        assert isinstance(_get_strategy("pre-push"), _PushStrategy)
        for delegated in ("commit-msg", "pre-merge-commit", "pre-rebase"):
            assert isinstance(_get_strategy(delegated), _DelegatedStrategy)

    def test_get_strategy_unknown_raises_value_error(self) -> None:
        from ac_guard.code_gate.core import _get_strategy

        with pytest.raises(ValueError, match="Unknown stage"):
            _get_strategy("post-commit")

    def test_push_strategy_shares_commit_strategy_instance(self) -> None:
        """Push strategy holds the same commit strategy instance the registry uses."""
        from ac_guard.code_gate.core import _STRATEGIES

        commit = _STRATEGIES["pre-commit"]
        push = _STRATEGIES["pre-push"]
        assert push._commit is commit
