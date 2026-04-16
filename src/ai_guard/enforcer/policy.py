"""Enforcer policy loader (E1 primitive).

Loads ``.ai-guard/policy.json`` and reconstructs a
:class:`BehaviorConfig` for runtime rule evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_guard.config.models import (
    BehaviorConfig,
    OperationRules,
    Rule,
)
from ai_guard.enforcer.exceptions import PolicyCorruptError

__all__ = ["load_policy"]

_POLICY_FILE = ".ai-guard/policy.json"


def load_policy(project_root: Path) -> tuple[BehaviorConfig, str] | None:
    """Load policy from ``.ai-guard/policy.json``.

    Args:
        project_root: Path to the project root directory.

    Returns:
        Tuple of (BehaviorConfig, config_hash) if policy exists,
        None if no policy file is installed (first-time use).

    Raises:
        PolicyCorruptError: If policy.json exists but cannot
            be parsed as valid JSON.
    """
    policy_path = project_root / _POLICY_FILE
    if not policy_path.is_file():
        return None

    try:
        data = json.loads(policy_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise PolicyCorruptError(str(policy_path), str(e)) from None

    config_hash = data.get("config_hash", "")
    behavior_raw = data.get("behavior", {})
    behavior = _deserialize_behavior(behavior_raw)
    return behavior, config_hash


def _deserialize_behavior(raw: dict[str, Any]) -> BehaviorConfig:
    """Reconstruct BehaviorConfig from serialized dict.

    Args:
        raw: Behavior dict from policy.json.

    Returns:
        BehaviorConfig with deserialized rules.
    """
    return BehaviorConfig(
        read=_deserialize_operation_rules(raw.get("read", {})),
        write=_deserialize_operation_rules(raw.get("write", {})),
        execute=_deserialize_operation_rules(raw.get("execute", {})),
    )


def _deserialize_operation_rules(raw: dict[str, Any]) -> OperationRules:
    """Reconstruct OperationRules from serialized dict.

    Args:
        raw: Operation rules dict from policy.json.

    Returns:
        OperationRules with deserialized rule lists.
    """
    return OperationRules(
        forbidden=[_deserialize_rule(r) for r in raw.get("forbidden", [])],
        require_approval=[
            _deserialize_rule(r) for r in raw.get("require_approval", [])
        ],
        allow=[_deserialize_rule(r) for r in raw.get("allow", [])],
    )


def _deserialize_rule(raw: dict[str, Any]) -> Rule:
    """Reconstruct Rule from serialized dict.

    Args:
        raw: Rule dict from policy.json.

    Returns:
        Rule with pattern, reason, message, regex, and source.
    """
    return Rule(
        pattern=raw["pattern"],
        reason=raw.get("reason"),
        message=raw.get("message"),
        regex=raw.get("regex", False),
        source=raw.get("source", "user"),
    )
