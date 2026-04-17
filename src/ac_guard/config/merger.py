"""Configuration multi-source merger for AI Code Guard (WP1.2c).

Combines built-in defaults, rulesets, and the project guard.yaml into
a single :class:`ResolvedConfig`.  Merge semantics follow the design
document section 5.3:

* **List fields** (forbidden / require_approval / allow) — append.
* **``remove`` list** — exact-match removal after all sources merged.
* **``checks`` dict** — deep merge (field-level override per key).
* **Scalar values** — latter source overrides former.
"""

from __future__ import annotations

import copy
import hashlib
import warnings
from pathlib import Path
from typing import Any

from ac_guard.config.exceptions import ConfigWarning
from ac_guard.config.loader import (
    RawConfig,
    load_config,
)
from ac_guard.config.models import (
    AuditConfig,
    BehaviorConfig,
    CheckItem,
    CodeConfig,
    LanguageTools,
    OperationRules,
    OutputConfig,
    PrReportConfig,
    ResolvedConfig,
    Rule,
)

__all__ = ["resolve_config"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BUILTIN_DEFAULTS: RawConfig = {  # type: ignore[typeddict-unknown-key]
    "version": 1,
    "project": {"name": "", "language": ""},
    "behavior": {
        "read": {},
        "write": {},
        "execute": {},
    },
    "code": {
        "commit": {"format": True, "naming": True, "checks": {}},
        "push": {"lint": True, "checks": {}},
    },
    "output": {
        "verbosity": "normal",
        "locale": "en",
        "audit": {"enabled": True, "path": ".ac-guard/audit.jsonl", "retention": 30},
        "pr_report": {
            "enabled": False,
            "platform": "github",
            "token_env": "GITHUB_TOKEN",
        },
    },
}

_SYSTEM_PROTECTION_PATTERNS: list[str] = [
    "file:guard.yaml",
    "file:.ac-guard/**",
    "file:.pre-commit-config.yaml",
    "file:.git/hooks/**",
]

# ---------------------------------------------------------------------------
# Low-level merge helpers (pure functions — never mutate inputs)
# ---------------------------------------------------------------------------


def _merge_raw_configs(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge *overlay* on top of *base*, returning a new dict."""
    merged: dict[str, Any] = copy.deepcopy(base)

    for key, value in overlay.items():
        if key == "behavior":
            merged["behavior"] = _merge_behavior(merged.get("behavior", {}), value)
        elif key == "code":
            merged["code"] = _merge_code(merged.get("code", {}), value)
        elif key == "output":
            merged["output"] = _merge_output(merged.get("output", {}), value)
        elif key == "languages":
            merged["languages"] = _merge_languages(merged.get("languages", {}), value)
        elif key == "project":
            merged["project"] = {**merged.get("project", {}), **value}
        else:
            # Scalars (version, build, rulesets, …) — latter wins
            merged[key] = copy.deepcopy(value)

    return merged


def _merge_behavior(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for op in ("read", "write", "execute"):
        if op in overlay:
            merged[op] = _merge_operation_rules(merged.get(op, {}), overlay[op])
    return merged


def _merge_operation_rules(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for tier in ("forbidden", "require_approval", "allow"):
        if tier in overlay:
            merged[tier] = merged.get(tier, []) + copy.deepcopy(overlay[tier])
    # Accumulate remove lists for later processing
    if "remove" in overlay:
        merged["remove"] = merged.get("remove", []) + copy.deepcopy(overlay["remove"])
    return merged


def _merge_code(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for stage in ("commit", "push"):
        if stage in overlay:
            merged[stage] = _merge_code_stage(merged.get(stage, {}), overlay[stage])
    return merged


def _merge_code_stage(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key == "checks":
            merged["checks"] = _deep_merge_checks(merged.get("checks", {}), value)
        else:
            # Scalar bools (format, naming, lint)
            merged[key] = value
    return merged


def _deep_merge_checks(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for name, check in overlay.items():
        if name in merged:
            merged[name] = {**merged[name], **copy.deepcopy(check)}
        else:
            merged[name] = copy.deepcopy(check)
    return merged


def _merge_output(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **copy.deepcopy(value)}
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_languages(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for lang, entry in overlay.items():
        if lang in merged:
            # Deep-merge the tools sub-dict
            base_tools = merged[lang].get("tools", {})
            overlay_tools = entry.get("tools", {})
            merged[lang] = {"tools": {**base_tools, **overlay_tools}}
        else:
            merged[lang] = copy.deepcopy(entry)
    return merged


# ---------------------------------------------------------------------------
# Source tagging
# ---------------------------------------------------------------------------


def _tag_rules(raw_config: dict[str, Any], source: str) -> None:
    """Inject ``_source`` into every rule dict in the behavior section.

    Mutates *raw_config* in place — call on a deep-copied dict.
    """
    behavior = raw_config.get("behavior", {})
    for op in ("read", "write", "execute"):
        op_rules = behavior.get(op, {})
        for tier in ("forbidden", "require_approval", "allow"):
            for rule in op_rules.get(tier, []):
                rule["_source"] = source


# ---------------------------------------------------------------------------
# System protection rules
# ---------------------------------------------------------------------------


def _inject_system_rules(merged: dict[str, Any]) -> None:
    """Add system protection rules into ``write.require_approval``.

    Mutates *merged* in place.
    """
    behavior = merged.setdefault("behavior", {})
    write = behavior.setdefault("write", {})
    ra = write.setdefault("require_approval", [])

    for pattern in _SYSTEM_PROTECTION_PATTERNS:
        ra.append({"pattern": pattern, "_source": "system"})


# ---------------------------------------------------------------------------
# Remove processing
# ---------------------------------------------------------------------------


def _process_removes(behavior: dict[str, Any]) -> None:
    """Process and strip ``remove`` lists from *behavior*.

    For each operation type, removes matching rules from the three tiers.
    Emits :class:`ConfigWarning` for:
    - remove targets that match no rule (possible typo)
    - remove targets that match a system-protected rule (immutable)

    Mutates *behavior* in place.
    """
    for op in ("read", "write", "execute"):
        op_rules = behavior.get(op, {})
        removes = op_rules.pop("remove", [])
        for remove_entry in removes:
            pattern = remove_entry.get("pattern", "")
            found = False
            for tier in ("forbidden", "require_approval", "allow"):
                rules_list: list[dict[str, Any]] = op_rules.get(tier, [])
                for rule in rules_list:
                    if rule.get("pattern") == pattern:
                        if rule.get("_source") == "system":
                            warnings.warn(
                                f"Cannot remove system-protected rule: {pattern}",
                                ConfigWarning,
                                stacklevel=2,
                            )
                            found = True
                            break
                        rules_list.remove(rule)
                        found = True
                        break
                if found:
                    break
            if not found:
                warnings.warn(
                    f"Remove target not found (possible typo): {pattern}",
                    ConfigWarning,
                    stacklevel=2,
                )


# ---------------------------------------------------------------------------
# RawConfig → ResolvedConfig conversion
# ---------------------------------------------------------------------------


def _to_resolved_config(
    merged: dict[str, Any],
    *,
    config_hash: str,
    default_project_name: str,
) -> ResolvedConfig:
    """Convert a merged raw dict tree into a :class:`ResolvedConfig`."""
    project = merged.get("project", {})
    return ResolvedConfig(
        version=merged.get("version", 1),
        project_name=project.get("name") or default_project_name,
        project_language=project.get("language", ""),
        behavior=_to_behavior(merged.get("behavior", {})),
        code=_to_code(merged.get("code", {})),
        languages=_to_languages(merged.get("languages", {})),
        output=_to_output(merged.get("output", {})),
        build_command=merged.get("build", {}).get("command"),
        config_hash=config_hash,
        rulesets=merged.get("rulesets", []),
    )


def _to_behavior(raw: dict[str, Any]) -> BehaviorConfig:
    return BehaviorConfig(
        read=_to_operation_rules(raw.get("read", {})),
        write=_to_operation_rules(raw.get("write", {})),
        execute=_to_operation_rules(raw.get("execute", {})),
    )


def _to_operation_rules(raw: dict[str, Any]) -> OperationRules:
    return OperationRules(
        forbidden=[_to_rule(r) for r in raw.get("forbidden", [])],
        require_approval=[_to_rule(r) for r in raw.get("require_approval", [])],
        allow=[_to_rule(r) for r in raw.get("allow", [])],
    )


def _to_rule(raw: dict[str, Any]) -> Rule:
    return Rule(
        pattern=raw["pattern"],
        reason=raw.get("reason"),
        message=raw.get("message"),
        regex=raw.get("regex", False),
        source=raw.get("_source", "user"),
    )


def _to_code(raw: dict[str, Any]) -> CodeConfig:
    commit = raw.get("commit", {})
    push = raw.get("push", {})
    return CodeConfig(
        commit_format=commit.get("format", True),
        commit_naming=commit.get("naming", True),
        commit_checks={
            name: _to_check_item(item)
            for name, item in commit.get("checks", {}).items()
        },
        push_lint=push.get("lint", True),
        push_checks={
            name: _to_check_item(item) for name, item in push.get("checks", {}).items()
        },
    )


def _to_check_item(raw: dict[str, Any]) -> CheckItem:
    return CheckItem(
        command=raw["command"],
        timeout=raw.get("timeout", 300),
        enabled=raw.get("enabled", True),
        types=raw.get("types"),
        pass_filenames=raw.get("pass_filenames", True),
    )


def _to_languages(raw: dict[str, Any]) -> dict[str, LanguageTools]:
    result: dict[str, LanguageTools] = {}
    for lang, entry in raw.items():
        tools = entry.get("tools", {})
        result[lang] = LanguageTools(
            format=tools.get("format", ""),
            lint=tools.get("lint", ""),
        )
    return result


def _to_output(raw: dict[str, Any]) -> OutputConfig:
    audit_raw = raw.get("audit", {})
    pr_raw = raw.get("pr_report", {})
    return OutputConfig(
        verbosity=raw.get("verbosity", "normal"),
        locale=raw.get("locale", "en"),
        audit=AuditConfig(
            enabled=audit_raw.get("enabled", True),
            path=audit_raw.get("path", ".ac-guard/audit.jsonl"),
            retention=audit_raw.get("retention", 30),
        ),
        pr_report=PrReportConfig(
            enabled=pr_raw.get("enabled", False),
            platform=pr_raw.get("platform", "github"),
            api_url=pr_raw.get("api_url"),
            token_env=pr_raw.get("token_env", "GITHUB_TOKEN"),
        ),
    )


# ---------------------------------------------------------------------------
# Config hash
# ---------------------------------------------------------------------------


def _compute_config_hash(path: Path) -> str:
    """SHA-256 of the guard.yaml file bytes, truncated to 8 hex chars."""
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_config(
    path: str | Path,
    *,
    rulesets: list[tuple[str, RawConfig]] | None = None,
) -> ResolvedConfig:
    """Load and merge all config sources into a :class:`ResolvedConfig`.

    Merge order (later wins):
    ``built-in defaults → rulesets[0] → … → rulesets[N] → guard.yaml``

    Args:
        path: Path to the project's ``guard.yaml``.
        rulesets: Pre-loaded rulesets as ``(name, raw_config)`` pairs,
            in merge order.  Defaults to an empty list.

    Returns:
        A fully populated :class:`ResolvedConfig`.

    Raises:
        ConfigFileNotFoundError: ``guard.yaml`` does not exist.
        ConfigSyntaxError: YAML parsing failed.
        ConfigValidationError: Schema validation failed.
    """
    resolved_path = Path(path)

    # 1. Load and validate the user's guard.yaml (may raise)
    user_config: dict[str, Any] = dict(load_config(resolved_path))

    # 2. Hash the source file for drift detection
    config_hash = _compute_config_hash(resolved_path)

    # 3. Start from built-in defaults
    merged = copy.deepcopy(_BUILTIN_DEFAULTS)
    _tag_rules(merged, "default")

    # 4. Merge rulesets in order
    for name, raw in rulesets or []:
        ruleset_copy: dict[str, Any] = copy.deepcopy(dict(raw))
        _tag_rules(ruleset_copy, f"ruleset:{name}")
        merged = _merge_raw_configs(merged, ruleset_copy)

    # 5. Merge user config
    user_copy: dict[str, Any] = copy.deepcopy(user_config)
    _tag_rules(user_copy, "user")
    merged = _merge_raw_configs(merged, user_copy)

    # 6. Inject system protection rules
    _inject_system_rules(merged)

    # 7. Process remove lists
    _process_removes(merged.get("behavior", {}))

    # 8. Convert to dataclasses
    default_project_name = resolved_path.parent.name
    return _to_resolved_config(
        merged,
        config_hash=config_hash,
        default_project_name=default_project_name,
    )
