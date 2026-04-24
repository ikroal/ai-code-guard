"""Action guard module — runtime behavior policy enforcement.

Provides pattern matching, tool classification, policy loading,
and the top-level evaluate() entry point for AI agent behavior
enforcement.
"""

from ac_guard.action_guard.classifier import classify
from ac_guard.action_guard.engine import evaluate
from ac_guard.action_guard.exceptions import ActionGuardError, PolicyCorruptError
from ac_guard.action_guard.matcher import (
    VALID_SCHEMES,
    Decision,
    MatchResult,
    PolicyDecision,
    evaluate_rules,
    find_matching_rule,
    matches,
    parse_pattern,
)
from ac_guard.action_guard.policy import load_policy

__all__ = [
    "Decision",
    "ActionGuardError",
    "MatchResult",
    "PolicyCorruptError",
    "PolicyDecision",
    "VALID_SCHEMES",
    "classify",
    "evaluate",
    "evaluate_rules",
    "find_matching_rule",
    "load_policy",
    "matches",
    "parse_pattern",
]
