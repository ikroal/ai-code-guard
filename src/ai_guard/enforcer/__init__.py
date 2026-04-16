"""Enforcer module — runtime behavior policy enforcement.

Provides pattern matching, tool classification, policy loading,
and the top-level evaluate() entry point for AI agent behavior
enforcement.
"""

from ai_guard.enforcer.classifier import classify
from ai_guard.enforcer.engine import evaluate
from ai_guard.enforcer.exceptions import EnforcerError, PolicyCorruptError
from ai_guard.enforcer.matcher import (
    VALID_SCHEMES,
    Decision,
    MatchResult,
    PolicyDecision,
    evaluate_rules,
    find_matching_rule,
    matches,
    parse_pattern,
)
from ai_guard.enforcer.policy import load_policy

__all__ = [
    "Decision",
    "EnforcerError",
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
