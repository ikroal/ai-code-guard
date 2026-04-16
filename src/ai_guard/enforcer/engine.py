"""Enforcer engine — top-level evaluate function.

Combines E1 (load_policy), E2 (classify), and E3/E4 (match + decide)
into a single entry point for runtime behavior enforcement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_guard.enforcer.classifier import classify
from ai_guard.enforcer.exceptions import PolicyCorruptError
from ai_guard.enforcer.matcher import Decision, MatchResult, evaluate_rules
from ai_guard.enforcer.policy import load_policy

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["evaluate"]


def evaluate(
    tool_name: str,
    tool_input: dict[str, Any],
    project_root: Path,
) -> MatchResult:
    """Evaluate a tool call against the installed policy.

    Orchestrates the full Enforcer pipeline:
    E1 (load_policy) -> E2 (classify) -> E3/E4 (match + decide).

    Args:
        tool_name: Tool name from the AI agent.
        tool_input: Tool arguments dict.
        project_root: Path to project root directory.

    Returns:
        MatchResult with the policy decision, matched rule,
        and tier information.
    """
    # E1: Load policy
    try:
        policy_result = load_policy(project_root)
    except PolicyCorruptError:
        return MatchResult(Decision.DENY, None, "error")

    if policy_result is None:
        # No policy installed — first-time use, allow all
        return MatchResult(Decision.ALLOW, None, "no_policy")

    behavior, _config_hash = policy_result

    # E2: Classify tool call
    operation, scheme, target = classify(tool_name, tool_input)

    if operation == "unknown":
        return MatchResult(Decision.ALLOW, None, "unknown_tool")

    # Select operation rules
    operation_rules = {
        "read": behavior.read,
        "write": behavior.write,
        "execute": behavior.execute,
    }.get(operation)

    if operation_rules is None:
        return MatchResult(Decision.ALLOW, None, "unknown_tool")

    # E3/E4: Match and decide
    return evaluate_rules(target, scheme, operation_rules)
