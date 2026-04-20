"""Tests for Enforcer engine — top-level evaluate() (E1+E2+E3/E4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ac_guard.enforcer.engine import evaluate
from ac_guard.enforcer.matcher import Decision, PolicyDecision


def _write_policy(project_root: Path, policy_data: dict) -> None:
    """Write a runtime.json file."""
    policy_dir = project_root / ".ac-guard"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "runtime.json").write_text(
        json.dumps(policy_data, indent=2), encoding="utf-8"
    )


def _standard_policy() -> dict:
    """Return a realistic policy dict."""
    return {
        "config_hash": "abcd1234",
        "behavior": {
            "read": {
                "forbidden": [
                    {
                        "pattern": "file:**/.env",
                        "reason": "secrets",
                        "source": "default",
                    },
                ],
                "require_approval": [],
                "allow": [],
            },
            "write": {
                "forbidden": [
                    {
                        "pattern": "file:.git/**",
                        "reason": "Git internals",
                        "source": "default",
                    },
                ],
                "require_approval": [
                    {
                        "pattern": "file:guard.yaml",
                        "message": "Config change",
                        "source": "system",
                    },
                ],
                "allow": [
                    {"pattern": "file:src/**", "source": "user"},
                ],
            },
            "execute": {
                "forbidden": [
                    {
                        "pattern": "shell:git push --force*",
                        "reason": "No force push",
                        "source": "default",
                    },
                ],
                "require_approval": [],
                "allow": [
                    {"pattern": "shell:git status*", "source": "default"},
                ],
            },
        },
    }


class TestEvaluateNoPolicy:
    """Tests when no policy is installed."""

    def test_no_policy_allows_all(self, tmp_path: Path) -> None:
        """Without runtime.json, all operations are allowed."""
        result = evaluate("Write", {"file_path": ".git/config"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "no_policy"

    def test_corrupt_policy_denies(self, tmp_path: Path) -> None:
        """Corrupt runtime.json results in deny."""
        policy_dir = tmp_path / ".ac-guard"
        policy_dir.mkdir(parents=True)
        (policy_dir / "runtime.json").write_text("{{invalid json", encoding="utf-8")
        result = evaluate("Write", {"file_path": "test.py"}, tmp_path)
        assert result.decision == Decision.DENY
        assert result.tier == "error"


class TestEvaluateFileOps:
    """Tests for file read/write evaluation."""

    def test_write_to_git_denied(self, tmp_path: Path) -> None:
        """Writing to .git/ is denied with full PolicyDecision fields."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Write", {"file_path": ".git/config"}, tmp_path)
        assert isinstance(result, PolicyDecision)
        assert result.decision == Decision.DENY
        assert result.operation == "write"
        assert result.scheme == "file"
        assert result.target == ".git/config"
        assert result.policy_hash == "abcd1234"

    def test_write_to_src_allowed(self, tmp_path: Path) -> None:
        """Writing to src/ is allowed."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Write", {"file_path": "src/main.py"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "allow"

    def test_write_to_config_asks(self, tmp_path: Path) -> None:
        """Writing to guard.yaml asks for approval."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Edit", {"file_path": "guard.yaml"}, tmp_path)
        assert result.decision == Decision.ASK

    def test_read_env_denied(self, tmp_path: Path) -> None:
        """Reading .env files is denied."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Read", {"file_path": "config/.env"}, tmp_path)
        assert result.decision == Decision.DENY

    def test_read_normal_file_allowed(self, tmp_path: Path) -> None:
        """Reading normal files is allowed (default)."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Read", {"file_path": "src/main.py"}, tmp_path)
        assert result.decision == Decision.ALLOW


class TestEvaluateShellOps:
    """Tests for shell command evaluation."""

    def test_force_push_denied(self, tmp_path: Path) -> None:
        """Force push is denied."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Bash", {"command": "git push --force origin"}, tmp_path)
        assert result.decision == Decision.DENY

    def test_git_status_allowed(self, tmp_path: Path) -> None:
        """Git status is allowed."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Bash", {"command": "git status"}, tmp_path)
        assert result.decision == Decision.ALLOW

    def test_unknown_command_default_allow(self, tmp_path: Path) -> None:
        """Unknown commands get default allow."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Bash", {"command": "npm install"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "default"


class TestEvaluateUnknownTool:
    """Tests for unknown tool handling."""

    def test_unknown_tool_allowed(self, tmp_path: Path) -> None:
        """Unknown tools are allowed."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("SomeFutureTool", {"arg": "val"}, tmp_path)
        assert result.decision == Decision.ALLOW
        assert result.tier == "unknown_tool"


def _bypass_policy() -> dict:
    """Policy that mirrors the 4 system bypass regex rules from #104."""
    return {
        "config_hash": "bypass",
        "behavior": {
            "read": {"forbidden": [], "require_approval": [], "allow": []},
            "write": {"forbidden": [], "require_approval": [], "allow": []},
            "execute": {
                "forbidden": [
                    {
                        "pattern": r"shell:SKIP=\S+\s+git\s+(?:commit|push)\b.*",
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": r"shell:git\s+.*-c\s+core\.hooks[Pp]ath=\S+.*",
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": (
                            r"shell:(?i)git\s+config\s.*core\.hookspath\s+\S+.*"
                        ),
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": r"shell:git\s+rebase\s+.*(?:--exec|-x\s+).*",
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": r"shell:CI=\S+\s+git\s+(?:commit|push)\b.*",
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": (
                            r"shell:git\s+push\s+.*--force(?:-with-lease)?\b.*"
                            r"\b(?:main|master)\b.*"
                        ),
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": (
                            r"shell:git\s+push\s+.*\b(?:main|master)\b.*"
                            r"--force(?:-with-lease)?\b.*"
                        ),
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": (
                            r"shell:git\s+push\s+.*-f\b.*\b(?:main|master)\b.*"
                        ),
                        "regex": True,
                        "source": "system",
                    },
                    {
                        "pattern": (r"shell:git\s+push\s+\S+\s+\+(?:main|master)\b.*"),
                        "regex": True,
                        "source": "system",
                    },
                ],
                "require_approval": [],
                "allow": [],
            },
        },
    }


class TestSystemBypassPatterns:
    """Regression for #104 + CI= / force-push hardening."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "SKIP=ruff git commit -m x",
            "SKIP=ruff,mypy git push origin main",
            "git -c core.hooksPath=/tmp commit -m x",
            "git -c user.name=X -c core.hooksPath=/tmp push",
            "git config core.hooksPath /tmp",
            "git config --local core.hooksPath /tmp/hooks",
            "git config --global core.hookspath /opt/hooks",
            'git rebase --exec "rm -rf /" HEAD~3',
            "git rebase -x 'echo pwned' HEAD~3",
            # CI= env-var bypass
            "CI=1 git commit -m x",
            "CI=true git push origin main",
            # force push to protected branch, flag before branch
            "git push --force origin main",
            "git push --force-with-lease origin master",
            # force push, flag after branch
            "git push origin main --force",
            "git push origin master --force-with-lease",
            # -f short form
            "git push -f origin main",
            # `+<branch>` shorthand
            "git push origin +main",
            "git push origin +master",
        ],
    )
    def test_bypass_command_denied(self, tmp_path: Path, cmd: str) -> None:
        _write_policy(tmp_path, _bypass_policy())
        result = evaluate("Bash", {"command": cmd}, tmp_path)
        assert result.decision == Decision.DENY, f"expected deny for {cmd!r}"

    @pytest.mark.parametrize(
        "cmd",
        [
            "SKIP=foo make test",
            "git -c user.name=Alice commit -m x",
            "git config --get core.hooksPath",
            "git config --unset core.hooksPath",
            "git config --list",
            "git rebase -i HEAD~3",
            "git rebase -X ours HEAD~3",
            # NOTE: plain `git commit -m 'x'` is intentionally omitted — it now
            # escalates to ASK via the hooks-not-installed guard rail when the
            # tmp_path repo has no pre-commit hook, covered in
            # TestHooksNotInstalledEscalation.
            "git push origin feature",
            # CI= without git should pass through
            "CI=1 pytest",
            # force push to feature branch (not protected) is fine
            "git push --force origin feature-x",
            "git push origin +feature-x",
        ],
    )
    def test_lookalike_command_allowed(self, tmp_path: Path, cmd: str) -> None:
        _write_policy(tmp_path, _bypass_policy())
        result = evaluate("Bash", {"command": cmd}, tmp_path)
        assert result.decision == Decision.ALLOW, f"expected allow for {cmd!r}"


class TestHooksNotInstalledEscalation:
    """Regression: git commit without pre-commit hooks installed → ASK."""

    @staticmethod
    def _install_pre_commit_hook(project_root: Path) -> None:
        """Write a hook file that mimics pre-commit's signature."""
        hooks = project_root / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "pre-commit").write_text(
            "#!/bin/sh\n# File generated by pre-commit: "
            "https://pre-commit.com\n# hook-impl\n",
            encoding="utf-8",
        )

    def test_git_commit_without_hooks_escalates_to_ask(self, tmp_path: Path) -> None:
        _write_policy(tmp_path, _standard_policy())
        # Explicitly allow git commit so only the hooks check could escalate
        policy = _standard_policy()
        policy["behavior"]["execute"]["allow"].append(
            {"pattern": "shell:git commit*", "source": "user"},
        )
        _write_policy(tmp_path, policy)

        result = evaluate("Bash", {"command": "git commit -m x"}, tmp_path)

        assert result.decision == Decision.ASK
        assert result.tier == "hooks_not_installed"
        assert result.matched_rule is not None
        assert "pre-commit" in (result.matched_rule.reason or "")

    def test_git_commit_with_hooks_installed_allows(self, tmp_path: Path) -> None:
        policy = _standard_policy()
        policy["behavior"]["execute"]["allow"].append(
            {"pattern": "shell:git commit*", "source": "user"},
        )
        _write_policy(tmp_path, policy)
        self._install_pre_commit_hook(tmp_path)

        result = evaluate("Bash", {"command": "git commit -m x"}, tmp_path)

        assert result.decision == Decision.ALLOW
        assert result.tier != "hooks_not_installed"

    def test_non_commit_command_not_affected(self, tmp_path: Path) -> None:
        """git status etc. should never trigger the hook escalation."""
        _write_policy(tmp_path, _standard_policy())
        result = evaluate("Bash", {"command": "git status"}, tmp_path)
        assert result.tier != "hooks_not_installed"

    def test_forbidden_rule_wins_over_hook_check(self, tmp_path: Path) -> None:
        """Forbidden-tier matches DENY even if pre-commit hooks are missing."""
        policy = _standard_policy()
        policy["behavior"]["execute"]["forbidden"].append(
            {
                "pattern": "shell:git commit --no-verify*",
                "reason": "--no-verify skips hooks",
                "source": "system",
            },
        )
        _write_policy(tmp_path, policy)
        # No pre-commit hook file exists — DENY must still win.
        result = evaluate(
            "Bash",
            {"command": "git commit --no-verify -m x"},
            tmp_path,
        )
        assert result.decision == Decision.DENY
        assert result.tier == "forbidden"

    def test_hook_present_but_not_precommit_signature_still_escalates(
        self, tmp_path: Path
    ) -> None:
        """A stub pre-commit hook without pre-commit's signature counts as missing."""
        policy = _standard_policy()
        policy["behavior"]["execute"]["allow"].append(
            {"pattern": "shell:git commit*", "source": "user"},
        )
        _write_policy(tmp_path, policy)
        hooks = tmp_path / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "pre-commit").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")

        result = evaluate("Bash", {"command": "git commit -m x"}, tmp_path)
        assert result.decision == Decision.ASK
        assert result.tier == "hooks_not_installed"


def _policy_with_audit(enabled: bool) -> dict:
    policy = _standard_policy()
    policy["audit"] = {
        "enabled": enabled,
        "path": ".ac-guard/audit.jsonl",
        "retention_days": 30,
    }
    return policy


class TestEvaluateAuditWiring:
    """Regression for #75: evaluate() writes audit when enabled."""

    def test_writes_audit_when_enabled(self, tmp_path: Path) -> None:
        _write_policy(tmp_path, _policy_with_audit(enabled=True))
        evaluate(
            "Write",
            {"file_path": "guard.yaml"},
            tmp_path,
            agent="claude-code",
        )
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert audit_path.is_file()
        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["agent"] == "claude-code"
        assert record["tool"] == "Write"
        assert record["decision"] == "ask"

    def test_does_not_audit_when_disabled(self, tmp_path: Path) -> None:
        _write_policy(tmp_path, _policy_with_audit(enabled=False))
        evaluate(
            "Write",
            {"file_path": "guard.yaml"},
            tmp_path,
            agent="claude-code",
        )
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert not audit_path.exists()

    def test_missing_audit_section_defaults_disabled(self, tmp_path: Path) -> None:
        """Legacy runtime.json without an audit section is treated as off."""
        _write_policy(tmp_path, _standard_policy())
        evaluate(
            "Write",
            {"file_path": "guard.yaml"},
            tmp_path,
            agent="claude-code",
        )
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert not audit_path.exists()

    def test_unknown_tool_skips_audit(self, tmp_path: Path) -> None:
        """Early return on unknown_tool must not write audit."""
        _write_policy(tmp_path, _policy_with_audit(enabled=True))
        evaluate("SomeFutureTool", {"arg": "val"}, tmp_path, agent="claude-code")
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        assert not audit_path.exists()

    def test_passes_agent_to_record(self, tmp_path: Path) -> None:
        _write_policy(tmp_path, _policy_with_audit(enabled=True))
        evaluate("Write", {"file_path": "guard.yaml"}, tmp_path, agent="cursor")
        audit_path = tmp_path / ".ac-guard" / "audit.jsonl"
        record = json.loads(
            audit_path.read_text(encoding="utf-8").strip().split("\n")[0]
        )
        assert record["agent"] == "cursor"
