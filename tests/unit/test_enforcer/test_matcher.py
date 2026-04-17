"""Tests for Enforcer pattern matching engine (WP2.1a)."""

from __future__ import annotations

import re

import pytest

from ac_guard.config.models import OperationRules, Rule
from ac_guard.enforcer.matcher import (
    VALID_SCHEMES,
    Decision,
    evaluate_rules,
    find_matching_rule,
    matches,
    parse_pattern,
)

# ---------------------------------------------------------------------------
# TestParsePattern
# ---------------------------------------------------------------------------


class TestParsePattern:
    """Tests for parse_pattern function."""

    def test_file_pattern(self) -> None:
        """Parse standard file pattern."""
        assert parse_pattern("file:*.py") == ("file", "*.py")

    def test_shell_pattern(self) -> None:
        """Parse shell command pattern."""
        assert parse_pattern("shell:git push*") == ("shell", "git push*")

    def test_mcp_pattern_with_nested_colon(self) -> None:
        """Parse MCP pattern with colon in body."""
        assert parse_pattern("mcp:memory:delete_*") == ("mcp", "memory:delete_*")

    def test_web_pattern_with_url(self) -> None:
        """Parse web pattern with URL containing colons."""
        assert parse_pattern("web:https://foo.com") == ("web", "https://foo.com")

    def test_no_colon_raises(self) -> None:
        """Pattern without colon raises ValueError."""
        with pytest.raises(ValueError, match="separator"):
            parse_pattern("noscheme")

    def test_unknown_scheme_raises(self) -> None:
        """Unknown scheme raises ValueError."""
        with pytest.raises(ValueError, match="scheme"):
            parse_pattern("ftp:something")

    def test_empty_string_raises(self) -> None:
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="separator"):
            parse_pattern("")

    def test_empty_body(self) -> None:
        """Pattern with empty body is valid."""
        assert parse_pattern("file:") == ("file", "")

    def test_valid_schemes(self) -> None:
        """VALID_SCHEMES contains the four supported schemes."""
        assert {"file", "shell", "mcp", "web"} == VALID_SCHEMES


# ---------------------------------------------------------------------------
# TestMatches
# ---------------------------------------------------------------------------


class TestMatches:
    """Tests for matches function."""

    def test_glob_file_matches(self) -> None:
        """Glob pattern matches target."""
        rule = Rule(pattern="file:*.py")
        assert matches("main.py", rule) is True

    def test_glob_file_no_match(self) -> None:
        """Glob pattern does not match different extension."""
        rule = Rule(pattern="file:*.py")
        assert matches("main.js", rule) is False

    def test_glob_recursive(self) -> None:
        """** matches nested paths."""
        rule = Rule(pattern="file:src/**")
        assert matches("src/foo/bar.py", rule) is True

    def test_glob_exact(self) -> None:
        """Exact pattern matches exactly."""
        rule = Rule(pattern="file:.env")
        assert matches(".env", rule) is True

    def test_glob_exact_no_partial(self) -> None:
        """Exact pattern does not match partial."""
        rule = Rule(pattern="file:.env")
        assert matches(".env.local", rule) is False

    def test_glob_double_star_prefix(self) -> None:
        """**/ prefix matches any directory depth."""
        rule = Rule(pattern="file:**/.env")
        assert matches("config/.env", rule) is True
        assert matches("deep/nested/dir/.env", rule) is True

    def test_shell_glob(self) -> None:
        """Shell command glob matching."""
        rule = Rule(pattern="shell:git push --force*")
        assert matches("git push --force origin", rule) is True
        assert matches("git push origin", rule) is False

    def test_regex_matches(self) -> None:
        """Regex pattern matches."""
        rule = Rule(pattern=r"shell:git\s+push\s+--force.*", regex=True)
        assert matches("git push --force origin", rule) is True

    def test_regex_no_match(self) -> None:
        """Regex pattern does not match."""
        rule = Rule(pattern=r"shell:git\s+push\s+--force.*", regex=True)
        assert matches("git pull", rule) is False

    def test_regex_fullmatch(self) -> None:
        """Regex uses fullmatch — partial matches fail."""
        rule = Rule(pattern=r"shell:git", regex=True)
        assert matches("git push", rule) is False

    def test_invalid_regex_raises(self) -> None:
        """Invalid regex raises re.error."""
        rule = Rule(pattern="file:[invalid", regex=True)
        with pytest.raises(re.error):
            matches("test", rule)

    def test_malformed_pattern_raises(self) -> None:
        """Pattern without scheme raises ValueError."""
        rule = Rule(pattern="no_scheme_here")
        with pytest.raises(ValueError, match="separator"):
            matches("test", rule)

    def test_case_sensitive(self) -> None:
        """Glob matching is case-sensitive."""
        rule = Rule(pattern="file:Makefile")
        assert matches("Makefile", rule) is True
        assert matches("makefile", rule) is False


# ---------------------------------------------------------------------------
# TestFindMatchingRule
# ---------------------------------------------------------------------------


class TestFindMatchingRule:
    """Tests for find_matching_rule function."""

    def test_first_match_wins(self) -> None:
        """Returns the first matching rule."""
        rules = [
            Rule(pattern="file:*.py", reason="first"),
            Rule(pattern="file:*.py", reason="second"),
        ]
        result = find_matching_rule("main.py", "file", rules)
        assert result is not None
        assert result.reason == "first"

    def test_scheme_filtering(self) -> None:
        """Skips rules with non-matching scheme."""
        rules = [
            Rule(pattern="shell:git*", reason="shell rule"),
            Rule(pattern="file:*.py", reason="file rule"),
        ]
        result = find_matching_rule("main.py", "file", rules)
        assert result is not None
        assert result.reason == "file rule"

    def test_empty_list(self) -> None:
        """Empty rule list returns None."""
        assert find_matching_rule("main.py", "file", []) is None

    def test_no_match(self) -> None:
        """No matching rule returns None."""
        rules = [Rule(pattern="file:*.js")]
        assert find_matching_rule("main.py", "file", rules) is None

    def test_mixed_glob_and_regex(self) -> None:
        """Mix of glob and regex rules in same list."""
        rules = [
            Rule(pattern="file:*.js"),
            Rule(pattern=r"file:main\.py", regex=True, reason="regex"),
        ]
        result = find_matching_rule("main.py", "file", rules)
        assert result is not None
        assert result.reason == "regex"


# ---------------------------------------------------------------------------
# TestEvaluateRules
# ---------------------------------------------------------------------------


class TestEvaluateRules:
    """Tests for evaluate_rules function."""

    def _rules(
        self,
        forbidden: list[Rule] | None = None,
        require_approval: list[Rule] | None = None,
        allow: list[Rule] | None = None,
    ) -> OperationRules:
        return OperationRules(
            forbidden=forbidden or [],
            require_approval=require_approval or [],
            allow=allow or [],
        )

    def test_forbidden_returns_deny(self) -> None:
        """Matching forbidden rule returns DENY."""
        rules = self._rules(forbidden=[Rule(pattern="file:.git/**")])
        result = evaluate_rules(".git/config", "file", rules)
        assert result.decision == Decision.DENY
        assert result.tier == "forbidden"
        assert result.matched_rule is not None

    def test_require_approval_returns_ask(self) -> None:
        """Matching require_approval rule returns ASK."""
        rules = self._rules(require_approval=[Rule(pattern="file:guard.yaml")])
        result = evaluate_rules("guard.yaml", "file", rules)
        assert result.decision == Decision.ASK
        assert result.tier == "require_approval"

    def test_allow_returns_allow(self) -> None:
        """Matching allow rule returns ALLOW."""
        rules = self._rules(allow=[Rule(pattern="file:src/**")])
        result = evaluate_rules("src/main.py", "file", rules)
        assert result.decision == Decision.ALLOW
        assert result.tier == "allow"

    def test_no_match_returns_default_allow(self) -> None:
        """No matching rule returns default ALLOW."""
        rules = self._rules(forbidden=[Rule(pattern="file:.git/**")])
        result = evaluate_rules("src/main.py", "file", rules)
        assert result.decision == Decision.ALLOW
        assert result.tier == "default"
        assert result.matched_rule is None

    def test_forbidden_over_require_approval(self) -> None:
        """Forbidden takes precedence over require_approval."""
        rules = self._rules(
            forbidden=[Rule(pattern="file:.git/**")],
            require_approval=[Rule(pattern="file:.git/**")],
        )
        result = evaluate_rules(".git/config", "file", rules)
        assert result.decision == Decision.DENY
        assert result.tier == "forbidden"

    def test_require_approval_over_allow(self) -> None:
        """Require_approval takes precedence over allow."""
        rules = self._rules(
            require_approval=[Rule(pattern="file:*.yaml")],
            allow=[Rule(pattern="file:*.yaml")],
        )
        result = evaluate_rules("config.yaml", "file", rules)
        assert result.decision == Decision.ASK
        assert result.tier == "require_approval"

    def test_regex_error_fail_closed(self) -> None:
        """Regex error results in DENY (fail-closed)."""
        rules = self._rules(forbidden=[Rule(pattern="file:[invalid", regex=True)])
        result = evaluate_rules("test.py", "file", rules)
        assert result.decision == Decision.DENY
        assert result.tier == "error"

    def test_malformed_pattern_fail_closed(self) -> None:
        """Malformed pattern results in DENY (fail-closed)."""
        rules = self._rules(forbidden=[Rule(pattern="no_colon")])
        result = evaluate_rules("test", "file", rules)
        assert result.decision == Decision.DENY
        assert result.tier == "error"

    def test_empty_rules_default_allow(self) -> None:
        """Empty OperationRules returns default ALLOW."""
        rules = OperationRules.empty()
        result = evaluate_rules("anything", "file", rules)
        assert result.decision == Decision.ALLOW
        assert result.tier == "default"


# ---------------------------------------------------------------------------
# TestRealisticScenarios
# ---------------------------------------------------------------------------


class TestRealisticScenarios:
    """Integration-style tests with realistic rule sets."""

    def _build_rules(self) -> OperationRules:
        """Build a realistic write OperationRules."""
        return OperationRules(
            forbidden=[
                Rule(pattern="file:.git/**", reason="Git internals"),
                Rule(pattern="file:vendor/**", reason="Third-party"),
            ],
            require_approval=[
                Rule(pattern="file:guard.yaml", message="Config change"),
                Rule(pattern="file:.github/workflows/**", message="CI change"),
            ],
            allow=[
                Rule(pattern="file:src/**"),
                Rule(pattern="file:tests/**"),
            ],
        )

    def test_write_to_src_allowed(self) -> None:
        """Writing to src/ is allowed."""
        result = evaluate_rules("src/main.py", "file", self._build_rules())
        assert result.decision == Decision.ALLOW
        assert result.tier == "allow"

    def test_write_to_git_denied(self) -> None:
        """Writing to .git/ is denied."""
        result = evaluate_rules(".git/config", "file", self._build_rules())
        assert result.decision == Decision.DENY

    def test_write_to_config_asks(self) -> None:
        """Writing to guard.yaml asks for approval."""
        result = evaluate_rules("guard.yaml", "file", self._build_rules())
        assert result.decision == Decision.ASK

    def test_write_to_unknown_default_allow(self) -> None:
        """Writing to unmatched path gets default allow."""
        result = evaluate_rules("README.md", "file", self._build_rules())
        assert result.decision == Decision.ALLOW
        assert result.tier == "default"

    def test_shell_execute_rules(self) -> None:
        """Shell command matching."""
        rules = OperationRules(
            forbidden=[
                Rule(pattern="shell:git push --force*"),
                Rule(pattern="shell:sudo *"),
            ],
            require_approval=[],
            allow=[
                Rule(pattern="shell:git status*"),
                Rule(pattern="shell:git diff*"),
            ],
        )
        assert (
            evaluate_rules("git push --force origin", "shell", rules).decision
            == Decision.DENY
        )
        assert evaluate_rules("git status", "shell", rules).decision == Decision.ALLOW
        assert (
            evaluate_rules("npm install", "shell", rules).decision == Decision.ALLOW
        )  # default

    def test_mcp_tool_matching(self) -> None:
        """MCP tool pattern matching."""
        rules = OperationRules(
            forbidden=[Rule(pattern="mcp:memory:delete_*")],
            require_approval=[],
            allow=[Rule(pattern="mcp:memory:search_*")],
        )
        assert (
            evaluate_rules("memory:delete_all", "mcp", rules).decision == Decision.DENY
        )
        assert (
            evaluate_rules("memory:search_query", "mcp", rules).decision
            == Decision.ALLOW
        )

    def test_scheme_isolation(self) -> None:
        """File rules don't match shell targets."""
        rules = OperationRules(
            forbidden=[Rule(pattern="file:.git/**")],
            require_approval=[],
            allow=[],
        )
        # ".git/config" as a shell target should not match file rules
        result = evaluate_rules(".git/config", "shell", rules)
        assert result.decision == Decision.ALLOW
        assert result.tier == "default"
