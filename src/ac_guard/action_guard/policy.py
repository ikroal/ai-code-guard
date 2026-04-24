"""Action guard policy loader (E1 primitive).

Loads ``.ac-guard/runtime.json`` and reconstructs a
:class:`BehaviorConfig` for runtime rule evaluation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ac_guard.action_guard.exceptions import PolicyCorruptError
from ac_guard.config import (
    AuditConfig,
    BehaviorConfig,
    OperationRules,
    Rule,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["load_policy"]

_RUNTIME_FILE = ".ac-guard/runtime.json"


def load_policy(
    project_root: Path,
) -> tuple[BehaviorConfig, str, AuditConfig] | None:
    """Load Action guard runtime cache from ``.ac-guard/runtime.json``.

    Args:
        project_root: Path to the project root directory.

    Returns:
        Tuple of (BehaviorConfig, config_hash, AuditConfig) if the
        cache exists, ``None`` if no runtime file is installed
        (first-time use). When the cache predates the audit section
        (legacy install), a disabled ``AuditConfig`` is returned so
        the caller can proceed without special-casing.

    Raises:
        PolicyCorruptError: If runtime.json exists but cannot
            be parsed as valid JSON.
    """
    runtime_path = project_root / _RUNTIME_FILE
    if not runtime_path.is_file():
        return None

    try:
        data = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise PolicyCorruptError(str(runtime_path), str(e)) from None

    config_hash = data.get("config_hash", "")
    behavior_raw = data.get("behavior", {})
    behavior = _deserialize_behavior(behavior_raw)
    audit = _deserialize_audit(data.get("audit"))
    return behavior, config_hash, audit


def _deserialize_audit(raw: dict[str, Any] | None) -> AuditConfig:
    """Reconstruct AuditConfig; missing section defaults to disabled."""
    if raw is None:
        return AuditConfig(enabled=False)
    return AuditConfig(
        enabled=bool(raw.get("enabled", False)),
        path=raw.get("path", ".ac-guard/audit.jsonl"),
        retention=int(raw.get("retention_days", 30)),
    )


def _deserialize_behavior(raw: dict[str, Any]) -> BehaviorConfig:
    """Reconstruct BehaviorConfig from serialized dict.

    Args:
        raw: Behavior dict from runtime.json.

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
        raw: Operation rules dict from runtime.json.

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
        raw: Rule dict from runtime.json.

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
