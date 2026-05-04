"""Configuration multi-source merger for AI Code Guard (WP1.2c).

Combines built-in defaults, rulesets, and the project guard.yaml into
a single :class:`ResolvedConfig`.  Merge semantics follow the design
document section 5.3:

* **List fields** (forbidden / require_approval / allow) — append.
* **``remove`` list** — exact-match removal after all sources merged.
* **``checks`` dict** — deep merge (field-level override per key).
* **Scalar values** — latter source overrides former.

Internal submodule — import the public surface via
:mod:`ac_guard.config` rather than reaching in here directly.
"""

from __future__ import annotations

import copy
import hashlib
import warnings
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ac_guard.config.exceptions import ConfigWarning
from ac_guard.config.loader import RawConfig, load_config

if TYPE_CHECKING:
    from collections.abc import Callable
from ac_guard.config.models import (
    AuditConfig,
    BehaviorConfig,
    CheckItem,
    CodeConfig,
    LanguageTools,
    OperationRules,
    OutputConfig,
    PreCommitHook,
    PreCommitMeta,
    PreCommitRepo,
    PrReportConfig,
    ResolvedConfig,
    Rule,
    StageBucket,
)
from ac_guard.config.semantic import (
    _PATTERN_UNIQUENESS,
    _TIER_CONSISTENCY,
    validate_semantic,
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
        "pre-commit": {"format": True, "lint": False, "checks": {}, "hooks": []},
        "commit-msg": {"format": False, "lint": False, "checks": {}, "hooks": []},
        "pre-merge-commit": {"format": False, "lint": False, "checks": {}, "hooks": []},
        "pre-push": {"format": False, "lint": True, "checks": {}, "hooks": []},
        "pre-rebase": {"format": False, "lint": False, "checks": {}, "hooks": []},
        "_extra": {"repos": []},
    },
    "output": {
        "verbosity": "normal",
        "locale": "en",
        "audit": {"enabled": True, "path": ".ac-guard/audit.jsonl", "retention": 30},
        "pr_report": {
            "enabled": False,
            "platform": "github",
            "token_env": "GITHUB_TOKEN",  # nosec B105 — env-var name, not a secret
        },
    },
}

_SYSTEM_PROTECTION_PATTERNS: list[str] = [
    "file:guard.yaml",
    "file:.ac-guard/**",
    "file:.pre-commit-config.yaml",
    "file:.git/hooks/**",
]

_SYSTEM_EXECUTE_FORBIDDEN: list[dict[str, Any]] = [
    {
        "pattern": "shell:git commit --no-verify*",
        "reason": "--no-verify skips pre-commit checks",
    },
    {
        "pattern": "shell:git push --no-verify*",
        "reason": "--no-verify skips pre-push checks",
    },
    {
        "pattern": r"shell:SKIP=\S+\s+git\s+(?:commit|push)\b.*",
        "regex": True,
        "reason": "SKIP= env-var bypasses pre-commit hooks",
    },
    {
        "pattern": r"shell:git\s+.*-c\s+core\.hooks[Pp]ath=\S+.*",
        "regex": True,
        "reason": "git -c core.hooksPath overrides the hook path",
    },
    {
        "pattern": r"shell:(?i)git\s+config\s.*core\.hookspath\s+\S+.*",
        "regex": True,
        "reason": "git config core.hooksPath permanently overrides the hook path",
    },
    {
        "pattern": r"shell:git\s+rebase\s+.*(?:--exec|-x\s+).*",
        "regex": True,
        "reason": (
            "git rebase --exec can run arbitrary commands bypassing per-commit hooks"
        ),
    },
    {
        "pattern": r"shell:CI=\S+\s+git\s+(?:commit|push)\b.*",
        "regex": True,
        "reason": "CI= env-var can trick tools into skipping pre-commit checks",
    },
    {
        "pattern": (
            r"shell:git\s+push\s+.*--force(?:-with-lease)?\b.*"
            r"\b(?:main|master)\b.*"
        ),
        "regex": True,
        "reason": "force push to protected branch rewrites shared history",
    },
    {
        "pattern": (
            r"shell:git\s+push\s+.*\b(?:main|master)\b.*"
            r"--force(?:-with-lease)?\b.*"
        ),
        "regex": True,
        "reason": "force push to protected branch rewrites shared history",
    },
    {
        "pattern": r"shell:git\s+push\s+.*-f\b.*\b(?:main|master)\b.*",
        "regex": True,
        "reason": "force push (-f) to protected branch rewrites shared history",
    },
    {
        "pattern": r"shell:git\s+push\s+\S+\s+\+(?:main|master)\b.*",
        "regex": True,
        "reason": (
            "git push <remote> +<branch> is an alias for force push to the "
            "protected branch"
        ),
    },
]

_DEFAULT_LANGUAGES_YAML = Path(__file__).parent / "defaults" / "languages.yaml"


@lru_cache(maxsize=1)
def _load_default_language_tools() -> dict[str, dict[str, str]]:
    """Read defaults/languages.yaml into a ``{lang: {format, lint}}`` map."""
    data = yaml.safe_load(_DEFAULT_LANGUAGES_YAML.read_text(encoding="utf-8")) or {}
    return {
        lang: {"format": entry.get("format", ""), "lint": entry.get("lint", "")}
        for lang, entry in data.items()
    }


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


_GATING_STAGES = (
    "pre-commit",
    "commit-msg",
    "pre-merge-commit",
    "pre-push",
    "pre-rebase",
)


def _merge_code(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for stage in _GATING_STAGES:
        if stage in overlay:
            merged[stage] = _merge_code_stage(merged.get(stage, {}), overlay[stage])
    # _extra.repos: append overlay repos (last-write-wins semantics not
    # meaningful for pre-commit repo lists; concatenate so ruleset-
    # provided extras survive the user's own declarations).
    if "_extra" in overlay:
        base_extra = merged.get("_extra", {"repos": []})
        overlay_repos = overlay["_extra"].get("repos", [])
        merged["_extra"] = {
            "repos": base_extra.get("repos", []) + copy.deepcopy(overlay_repos)
        }
    return merged


def _merge_code_stage(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key == "checks":
            merged["checks"] = _deep_merge_checks(merged.get("checks", {}), value)
        elif key == "hooks":
            # Append external repo lists: ruleset hooks + user hooks
            # coexist. Dedup by (repo, rev) last-wins.
            merged["hooks"] = _merge_precommit_repos(merged.get("hooks", []), value)
        else:
            # Scalar bools (format, lint)
            merged[key] = value
    return merged


def _merge_precommit_repos(
    base: list[dict[str, Any]], overlay: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Concatenate two pre-commit repos lists, deduping by (repo, rev).

    When the same (repo, rev) pair appears in both, the overlay's entry
    replaces the base — hooks list and any other fields are taken from
    the overlay, letting user guard.yaml override ruleset defaults.
    """
    result: list[dict[str, Any]] = [copy.deepcopy(r) for r in base]
    by_key = {(r.get("repo"), r.get("rev")): i for i, r in enumerate(result)}
    for repo in overlay:
        key = (repo.get("repo"), repo.get("rev"))
        copied = copy.deepcopy(repo)
        if key in by_key:
            result[by_key[key]] = copied
        else:
            by_key[key] = len(result)
            result.append(copied)
    return result


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
    """Add non-removable system-protection rules to *merged*.

    Injects two disjoint sets:

    * ``write.require_approval`` — paths that guard the guardrails
      themselves (``_SYSTEM_PROTECTION_PATTERNS``).
    * ``execute.forbidden`` — commands that would bypass the guard
      (``_SYSTEM_EXECUTE_FORBIDDEN``).

    Mutates *merged* in place.
    """
    behavior = merged.setdefault("behavior", {})

    write = behavior.setdefault("write", {})
    ra = write.setdefault("require_approval", [])
    for pattern in _SYSTEM_PROTECTION_PATTERNS:
        ra.append({"pattern": pattern, "_source": "system"})

    execute = behavior.setdefault("execute", {})
    forbidden = execute.setdefault("forbidden", [])
    for entry in _SYSTEM_EXECUTE_FORBIDDEN:
        forbidden.append({**entry, "_source": "system"})


def _auto_populate_languages(merged: dict[str, Any]) -> None:
    """Fill ``languages`` from ``project.language`` when user left it empty.

    When a user writes ``project.language: python`` without an explicit
    ``languages`` section, ``format`` / ``lint`` shortcuts would otherwise
    have no tools to invoke. We look the language up in
    ``defaults/languages.yaml`` and, if present, inject the built-in tool
    mapping so the commit / push checks work out of the box.

    Mutates *merged* in place.
    """
    existing = merged.get("languages")
    if existing:
        return
    lang = (merged.get("project") or {}).get("language")
    if not lang:
        return
    defaults = _load_default_language_tools()
    tools = defaults.get(lang)
    if tools is None:
        return
    merged["languages"] = {lang: {"tools": dict(tools)}}


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
        pre_commit_meta=_to_pre_commit_meta(merged.get("_pre_commit", {})),
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
    buckets: dict[str, StageBucket] = {}
    for stage in _GATING_STAGES:
        raw_bucket = raw.get(stage, {})
        buckets[stage] = _to_stage_bucket(raw_bucket)
    extra_repos = [
        _to_precommit_repo(r) for r in raw.get("_extra", {}).get("repos", [])
    ]
    # Map yaml hyphenated stage names to Python attribute names.
    return CodeConfig(
        pre_commit=buckets["pre-commit"],
        commit_msg=buckets["commit-msg"],
        pre_merge_commit=buckets["pre-merge-commit"],
        pre_push=buckets["pre-push"],
        pre_rebase=buckets["pre-rebase"],
        extra_repos=extra_repos,
    )


def _to_stage_bucket(raw: dict[str, Any]) -> StageBucket:
    return StageBucket(
        format=bool(raw.get("format", False)),
        lint=bool(raw.get("lint", False)),
        checks={
            name: _to_check_item(item) for name, item in raw.get("checks", {}).items()
        },
        hooks=[_to_precommit_repo(r) for r in raw.get("hooks", [])],
    )


def _to_precommit_repo(raw: dict[str, Any]) -> PreCommitRepo:
    return PreCommitRepo(
        repo=raw["repo"],
        rev=raw.get("rev"),
        hooks=[_to_precommit_hook(h) for h in raw.get("hooks", [])],
    )


def _to_precommit_hook(raw: dict[str, Any]) -> PreCommitHook:
    extra = {k: v for k, v in raw.items() if k != "id"}
    return PreCommitHook(id=raw["id"], extra=extra)


def _to_pre_commit_meta(raw: dict[str, Any]) -> PreCommitMeta:
    return PreCommitMeta(
        minimum_version=raw.get("minimum_version"),
        default_install_hook_types=raw.get("default_install_hook_types"),
        default_language_version=dict(raw.get("default_language_version", {})),
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
            token_env=pr_raw.get("token_env", "GITHUB_TOKEN"),  # nosec B105
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
    rulesets: list[tuple[str, dict[str, Any]]] | None = None,
    fetch_rulesets: Callable[[list[str]], list[tuple[str, dict[str, Any]]]]
    | None = None,
) -> ResolvedConfig:
    """Load and merge all config sources into a :class:`ResolvedConfig`.

    Merge order (later wins):
    ``built-in defaults → rulesets[0] → … → rulesets[N] → guard.yaml``

    Args:
        path: Path to the project's ``guard.yaml``.
        rulesets: Pre-fetched ``(name, raw_dict)`` pairs in merge
            order. White-box convenience for tests and callers that
            already have ruleset data on hand.
        fetch_rulesets: Optional callback. When the user's
            ``guard.yaml`` declares a non-empty ``rulesets`` list, the
            callback is invoked with those names and must return
            ``(name, raw_dict)`` pairs in merge order. Lets callers
            control **where** rulesets come from (cache, remote git,
            custom store, …) without peeking at the raw yaml first.

        Pass at most one of the two; passing both raises ``TypeError``.

    Returns:
        A fully populated :class:`ResolvedConfig`.

    Raises:
        ConfigFileNotFoundError: ``guard.yaml`` does not exist.
        ConfigSyntaxError: YAML parsing failed.
        ConfigValidationError: Schema validation failed.
        TypeError: Both ``rulesets`` and ``fetch_rulesets`` were given.
    """
    if rulesets is not None and fetch_rulesets is not None:
        raise TypeError(
            "resolve_config(): pass at most one of 'rulesets' or 'fetch_rulesets'"
        )
    resolved_path = Path(path)

    # 1. Load and validate the user's guard.yaml (may raise)
    user_config: dict[str, Any] = dict(load_config(resolved_path))

    # 2. Hash the source file for drift detection
    config_hash = _compute_config_hash(resolved_path)

    # 3. Start from built-in defaults
    merged = copy.deepcopy(_BUILTIN_DEFAULTS)
    _tag_rules(merged, "default")

    # 4. Resolve ruleset pairs (callback-driven or pre-fetched) and merge
    ruleset_pairs: list[tuple[str, dict[str, Any]]] = list(rulesets or [])
    if fetch_rulesets is not None:
        declared = list(user_config.get("rulesets") or [])
        if declared:
            ruleset_pairs = list(fetch_rulesets(declared))
    for name, raw in ruleset_pairs:
        ruleset_copy: dict[str, Any] = copy.deepcopy(dict(raw))
        _tag_rules(ruleset_copy, f"ruleset:{name}")
        merged = _merge_raw_configs(merged, ruleset_copy)

    # 5. Merge user config
    user_copy: dict[str, Any] = copy.deepcopy(user_config)
    _tag_rules(user_copy, "user")
    merged = _merge_raw_configs(merged, user_copy)

    # 6. Auto-populate languages from project.language + defaults when empty
    _auto_populate_languages(merged)

    # 7. Inject system protection rules
    _inject_system_rules(merged)

    # 8. Process remove lists
    _process_removes(merged.get("behavior", {}))

    # 9. Convert to dataclasses
    default_project_name = resolved_path.parent.name
    resolved = _to_resolved_config(
        merged,
        config_hash=config_hash,
        default_project_name=default_project_name,
    )

    # 10. Semantic rules judging the merged tree (zero IO).
    validate_semantic(resolved, [_TIER_CONSISTENCY, _PATTERN_UNIQUENESS])

    return resolved
