"""Enforcer engine — top-level evaluate function.

Combines E1 (load_policy), E2 (classify), and E3/E4 (match + decide)
into a single entry point for runtime behavior enforcement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_guard.enforcer.classifier import classify
from ai_guard.enforcer.exceptions import PolicyCorruptError
from ai_guard.enforcer.matcher import Decision, PolicyDecision, evaluate_rules
from ai_guard.enforcer.policy import load_policy

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["evaluate"]


def evaluate(
    tool_name: str,
    tool_input: dict[str, Any],
    project_root: Path,
) -> PolicyDecision:
    """Evaluate a tool call against the installed policy.

    Orchestrates the full Enforcer pipeline:
    E1 (load_policy) -> E2 (classify) -> E3/E4 (match + decide).

    Args:
        tool_name: Tool name from the AI agent.
        tool_input: Tool arguments dict.
        project_root: Path to project root directory.

    Returns:
        PolicyDecision with the decision, classification context,
        matched rule, and policy hash for audit logging.
    """
    # E1: Load policy
    try:
        policy_result = load_policy(project_root)
    except PolicyCorruptError:
        return PolicyDecision(
            decision=Decision.DENY,
            operation="",
            scheme="",
            target="",
            matched_rule=None,
            tier="error",
            policy_hash="",
        )

    if policy_result is None:
        return PolicyDecision(
            decision=Decision.ALLOW,
            operation="",
            scheme="",
            target="",
            matched_rule=None,
            tier="no_policy",
            policy_hash="",
        )

    behavior, config_hash = policy_result

    # E2: Classify tool call
    operation, scheme, target = classify(tool_name, tool_input)

    if operation == "unknown":
        return PolicyDecision(
            decision=Decision.ALLOW,
            operation=operation,
            scheme=scheme,
            target=target,
            matched_rule=None,
            tier="unknown_tool",
            policy_hash=config_hash,
        )

    # Select operation rules
    operation_rules = {
        "read": behavior.read,
        "write": behavior.write,
        "execute": behavior.execute,
    }.get(operation)

    if operation_rules is None:
        return PolicyDecision(
            decision=Decision.ALLOW,
            operation=operation,
            scheme=scheme,
            target=target,
            matched_rule=None,
            tier="unknown_tool",
            policy_hash=config_hash,
        )

    # E3/E4: Match and decide
    match_result = evaluate_rules(target, scheme, operation_rules)

    return PolicyDecision(
        decision=match_result.decision,
        operation=operation,
        scheme=scheme,
        target=target,
        matched_rule=match_result.matched_rule,
        tier=match_result.tier,
        policy_hash=config_hash,
    )
