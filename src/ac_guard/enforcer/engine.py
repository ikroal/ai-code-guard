"""Enforcer engine — top-level evaluate function.

Combines E1 (load_policy), E2 (classify), and E3/E4 (match + decide)
into a single entry point for runtime behavior enforcement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ac_guard.enforcer.classifier import classify
from ac_guard.enforcer.exceptions import PolicyCorruptError
from ac_guard.enforcer.matcher import Decision, PolicyDecision, evaluate_rules
from ac_guard.enforcer.policy import load_policy
from ac_guard.reporter.audit import append_audit_log

if TYPE_CHECKING:
    from pathlib import Path

    from ac_guard.config.models import AuditConfig

__all__ = ["evaluate"]


def evaluate(
    tool_name: str,
    tool_input: dict[str, Any],
    project_root: Path,
    agent: str = "",
) -> PolicyDecision:
    """Evaluate a tool call against the installed policy.

    Orchestrates the full Enforcer pipeline:
    E1 (load_policy) -> E2 (classify) -> E3/E4 (match + decide) ->
    R3 (append_audit_log when enabled).

    Args:
        tool_name: Tool name from the AI agent.
        tool_input: Tool arguments dict.
        project_root: Path to project root directory.
        agent: Identifier of the invoking agent (``"claude-code"``,
            ``"cursor"``, ``"opencode"``, ...). Empty string is
            accepted for backward-compatible callers but leaves the
            audit record's ``agent`` field empty.

    Returns:
        PolicyDecision with the decision, classification context,
        matched rule, and policy hash for audit logging.
    """
    # E1: Load policy
    try:
        policy_result = load_policy(project_root)
    except PolicyCorruptError:
        # Fail-closed: deny without auditing (no policy context means
        # no trustworthy audit record anyway).
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

    behavior, config_hash, audit_cfg = policy_result

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

    decision = PolicyDecision(
        decision=match_result.decision,
        operation=operation,
        scheme=scheme,
        target=target,
        matched_rule=match_result.matched_rule,
        tier=match_result.tier,
        policy_hash=config_hash,
    )

    # R3: Audit. Only real decisions (post-classify, post-match) are
    # audited — early returns on "corrupt", "no_policy", and
    # "unknown_tool" are intentionally skipped.
    _maybe_audit(decision, tool_name, agent, project_root, audit_cfg)

    return decision


def _maybe_audit(
    decision: PolicyDecision,
    tool_name: str,
    agent: str,
    project_root: Path,
    audit_cfg: AuditConfig,
) -> None:
    """Append an audit record when auditing is enabled."""
    if not audit_cfg.enabled:
        return
    record = decision.to_audit_record(tool_name, agent)
    append_audit_log(record, project_root, audit_cfg.path)
