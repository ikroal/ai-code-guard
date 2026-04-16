"""Enforcer pattern matching engine (E3 primitive).

Parses ``{scheme}:{body}`` patterns, matches resource targets against
rules using glob or regex, and evaluates three-tier decision logic
(forbidden > require_approval > allow > default allow).

Fail-closed: any matching error (regex syntax, malformed pattern)
results in a DENY decision.
"""

from __future__ import annotations

import enum
import fnmatch
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_guard.config.models import OperationRules, Rule

__all__ = [
    "Decision",
    "MatchResult",
    "PolicyDecision",
    "VALID_SCHEMES",
    "evaluate_rules",
    "find_matching_rule",
    "matches",
    "parse_pattern",
]

VALID_SCHEMES = frozenset({"file", "shell", "mcp", "web"})


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class Decision(enum.Enum):
    """Result of three-tier rule evaluation.

    Attributes:
        ALLOW: Operation proceeds without restriction.
        DENY: Operation is blocked.
        ASK: User is prompted for confirmation.
    """

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class MatchResult:
    """Outcome of evaluate_rules().

    Attributes:
        decision: The policy decision (allow/deny/ask).
        matched_rule: The rule that triggered the decision,
            or None if no rule matched (default allow).
        tier: Which tier matched: "forbidden",
            "require_approval", "allow", "default", or "error".
    """

    decision: Decision
    matched_rule: Rule | None
    tier: str


@dataclass
class PolicyDecision:
    """Full decision with classification context for audit logging.

    Extends MatchResult with operation classification and policy
    hash for complete audit trail recording.

    Attributes:
        decision: The policy decision (allow/deny/ask).
        operation: Classified operation type.
        scheme: Resource scheme type.
        target: Extracted resource identifier.
        matched_rule: The rule that triggered the decision,
            or None if no rule matched.
        tier: Which tier matched.
        policy_hash: Config hash from policy.json.
    """

    decision: Decision
    operation: str
    scheme: str
    target: str
    matched_rule: Rule | None
    tier: str
    policy_hash: str

    def to_audit_record(self, tool_name: str, agent: str) -> dict[str, str | None]:
        """Build audit record dict for Reporter.

        Args:
            tool_name: Original tool name from the AI agent.
            agent: Agent identifier (e.g., "claude-code").

        Returns:
            Dict with all audit fields (except timestamp).
        """
        reason = None
        pattern = None
        if self.matched_rule is not None:
            reason = self.matched_rule.reason or self.matched_rule.message
            pattern = self.matched_rule.pattern
        return {
            "agent": agent,
            "tool": tool_name,
            "operation": self.operation,
            "scheme": self.scheme,
            "target": self.target,
            "decision": self.decision.value,
            "reason": reason,
            "matched_rule": pattern,
            "policy_hash": self.policy_hash,
        }


# ---------------------------------------------------------------------------
# Layer 1: Pattern parsing
# ---------------------------------------------------------------------------


def parse_pattern(pattern: str) -> tuple[str, str]:
    """Parse a pattern string into (scheme, body).

    Splits on the first ``:``. Validates that the scheme is one
    of the recognized types.

    Args:
        pattern: Pattern string in ``{scheme}:{body}`` format.

    Returns:
        Tuple of (scheme, pattern_body).

    Raises:
        ValueError: If pattern has no ``:`` separator or scheme
            is not recognized.
    """
    if ":" not in pattern:
        msg = f"Pattern missing ':' separator: {pattern!r}"
        raise ValueError(msg)

    scheme, body = pattern.split(":", 1)
    scheme = scheme.strip().lower()

    if scheme not in VALID_SCHEMES:
        msg = f"Unknown scheme {scheme!r}. Valid: {sorted(VALID_SCHEMES)}"
        raise ValueError(msg)

    return scheme, body


# ---------------------------------------------------------------------------
# Layer 2: Single-rule matching
# ---------------------------------------------------------------------------


def matches(target: str, rule: Rule) -> bool:
    """Test whether a target string matches a rule's pattern.

    For glob rules (``rule.regex`` is False): uses
    ``fnmatch.fnmatchcase()`` for case-sensitive matching.

    For regex rules (``rule.regex`` is True): uses
    ``re.fullmatch()`` (anchored at both start and end).

    Args:
        target: The resource string to match (e.g.,
            ``"src/main.py"``, ``"git push --force"``).
        rule: The rule containing the pattern and mode.

    Returns:
        True if the target matches the pattern body.

    Raises:
        re.error: If regex compilation fails.
        ValueError: If pattern format is invalid.
    """
    _scheme, body = parse_pattern(rule.pattern)

    if rule.regex:
        return re.fullmatch(body, target) is not None

    return fnmatch.fnmatchcase(target, body)


# ---------------------------------------------------------------------------
# Layer 3: First-match search
# ---------------------------------------------------------------------------


def find_matching_rule(
    target: str,
    scheme: str,
    rules: list[Rule],
) -> Rule | None:
    """Find the first rule that matches the target.

    Only considers rules whose scheme matches the given scheme.

    Args:
        target: The resource string to match.
        scheme: The scheme to filter by (e.g., ``"file"``).
        rules: Ordered list of rules to check.

    Returns:
        The first matching Rule, or None.

    Raises:
        ValueError: If a rule's pattern is malformed.
        re.error: If a regex rule has invalid syntax.
    """
    for rule in rules:
        rule_scheme, _body = parse_pattern(rule.pattern)
        if rule_scheme != scheme:
            continue
        if matches(target, rule):
            return rule
    return None


# ---------------------------------------------------------------------------
# Layer 4: Three-tier decision
# ---------------------------------------------------------------------------


def evaluate_rules(
    target: str,
    scheme: str,
    operation_rules: OperationRules,
) -> MatchResult:
    """Evaluate three-tier rules and return a policy decision.

    Checks tiers in precedence order:

    1. ``forbidden`` -> DENY
    2. ``require_approval`` -> ASK
    3. ``allow`` -> ALLOW
    4. No match -> ALLOW (default)

    Fail-closed: any exception during matching results in DENY.

    Args:
        target: The resource string to match.
        scheme: The scheme type (e.g., ``"file"``).
        operation_rules: The three-tier rule set to evaluate.

    Returns:
        MatchResult with the decision, matched rule, and tier.
    """
    try:
        # Tier 1: forbidden -> DENY
        rule = find_matching_rule(target, scheme, operation_rules.forbidden)
        if rule is not None:
            return MatchResult(Decision.DENY, rule, "forbidden")

        # Tier 2: require_approval -> ASK
        rule = find_matching_rule(target, scheme, operation_rules.require_approval)
        if rule is not None:
            return MatchResult(Decision.ASK, rule, "require_approval")

        # Tier 3: allow -> ALLOW
        rule = find_matching_rule(target, scheme, operation_rules.allow)
        if rule is not None:
            return MatchResult(Decision.ALLOW, rule, "allow")

    except Exception:
        # Fail-closed: any error -> DENY
        return MatchResult(Decision.DENY, None, "error")

    # Default: ALLOW
    return MatchResult(Decision.ALLOW, None, "default")
