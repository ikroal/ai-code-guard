"""Schema and semantic validation for guard.yaml configuration.

Validates a raw config dict (parsed from YAML) against the guard.yaml
schema. Collects all validation issues and raises once, so the user
can fix every problem in a single pass.

Internal submodule — import the public surface via
:mod:`ac_guard.config` rather than reaching in here directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ac_guard.config.exceptions import ConfigValidationError, ValidationIssue
from ac_guard.domain.languages import TYPE_EXTENSIONS
from ac_guard.domain.stages import KNOWN_STAGES

__all__ = ["validate_raw_config"]

# --- Schema node types ---
# 6 types: Str, Int, Bool (scalars) + Dict, DynDict, List (structures)
# Each type only carries fields relevant to its role, eliminating
# invalid combinations like Str(min_value=0) or Scalar(type=int, non_empty=True).


@dataclass(frozen=True)
class Str:
    """String scalar node.

    Attributes:
        non_empty: Reject empty strings.
        enum: Allowed values (frozenset of strings).
    """

    non_empty: bool = False
    enum: frozenset[str] | None = None


@dataclass(frozen=True)
class Int:
    """Integer scalar node. Naturally rejects bool (bool is int subclass).

    Attributes:
        enum: Allowed values (frozenset of integers).
        min_value: Minimum value.
        min_exclusive: If True, require strictly greater than min_value.
    """

    enum: frozenset[int] | None = None
    min_value: int | None = None
    min_exclusive: bool = False


@dataclass(frozen=True)
class Bool:
    """Boolean scalar node. No constraints."""


@dataclass(frozen=True)
class Dict:
    """Fixed-key mapping node (e.g. project, output).

    Attributes:
        fields: Schema for each allowed key.
        required: Keys that must be present.
        check_regex: Special flag for rule nodes to validate regex patterns.
        allow_unknown: Accept and skip validation for unknown keys. Used
            for pre-commit hook passthrough where ac-guard shouldn't
            enforce a fixed field list (pre-commit may add new fields).
    """

    fields: dict[str, SchemaNode]
    required: frozenset[str] = frozenset()
    check_regex: bool = False
    allow_unknown: bool = False


@dataclass(frozen=True)
class DynDict:
    """Dynamic-key mapping node (e.g. languages.*, checks.*).

    Attributes:
        values: Schema for each value (keys are arbitrary).
        key_enum: Optional whitelist of allowed keys. ``None`` means
            keys are unconstrained (e.g. ``checks.<custom-name>``);
            a ``frozenset`` rejects any key not in it (e.g. ``languages``
            keys must be in :data:`ac_guard.domain.languages.TYPE_EXTENSIONS`).
    """

    values: SchemaNode
    key_enum: frozenset[str] | None = None


@dataclass(frozen=True)
class List:
    """List node.

    Attributes:
        items: Schema for each element.
    """

    items: SchemaNode


SchemaNode = Str | Int | Bool | Dict | DynDict | List

# --- Schema definition ---
# Complete guard.yaml schema as a data tree. Adding new fields
# only requires modifying this tree, not adding new methods.


# Reusable sub-schemas
_RULE = Dict(
    fields={
        "pattern": Str(non_empty=True),
        "reason": Str(),
        "message": Str(),
        "regex": Bool(),
    },
    required=frozenset({"pattern"}),
    check_regex=True,
)

_OPERATION = Dict(
    fields={
        tier: List(items=_RULE)
        for tier in ("forbidden", "require_approval", "allow", "remove")
    }
)

_CHECK_ITEM = Dict(
    fields={
        "command": Str(),
        "timeout": Int(min_value=0, min_exclusive=True),
        "enabled": Bool(),
        "types": List(items=Str()),
        "pass_filenames": Bool(),
    },
    required=frozenset({"command"}),
)

_LANGUAGE_TOOLS = Dict(
    fields={"format": Str(), "lint": Str()},
    required=frozenset({"format", "lint"}),
)

_LANGUAGE_ENTRY = Dict(
    fields={"tools": _LANGUAGE_TOOLS},
    required=frozenset({"tools"}),
)

_PRECOMMIT_HOOK = Dict(
    # id is required; everything else passes through (schema is lenient
    # so new pre-commit fields work without ac-guard updates).
    fields={"id": Str(non_empty=True)},
    required=frozenset({"id"}),
    allow_unknown=True,
)

_PRECOMMIT_REPO = Dict(
    fields={
        "repo": Str(non_empty=True),
        "rev": Str(),
        "hooks": List(items=_PRECOMMIT_HOOK),
    },
    required=frozenset({"repo"}),
)

# Every gating-stage bucket has the same shape. `naming` is intentionally
# absent — D8 removed the dead flag; `lint: true` (via ruff N-rules)
# covers what naming used to try to do.
_STAGE_BUCKET = Dict(
    fields={
        "format": Bool(),
        "lint": Bool(),
        "checks": DynDict(values=_CHECK_ITEM),
        "hooks": List(items=_PRECOMMIT_REPO),
    }
)

_EXTRA = Dict(fields={"repos": List(items=_PRECOMMIT_REPO)})

_AUDIT_CONFIG = Dict(
    fields={
        "enabled": Bool(),
        "path": Str(),
        "retention": Int(min_value=0),
    }
)

_PR_REPORT_CONFIG = Dict(
    fields={
        "enabled": Bool(),
        "platform": Str(enum=frozenset({"github", "gitlab", "gitea", "bitbucket"})),
        "api_url": Str(),
        "token_env": Str(),
    }
)

_OUTPUT_CONFIG = Dict(
    fields={
        "verbosity": Str(enum=frozenset({"quiet", "normal", "verbose"})),
        "locale": Str(enum=frozenset({"en", "zh-CN"})),
        "audit": _AUDIT_CONFIG,
        "pr_report": _PR_REPORT_CONFIG,
    }
)

_PROJECT_CONFIG = Dict(
    fields={
        "name": Str(),
        "language": Str(non_empty=True, enum=frozenset(TYPE_EXTENSIONS)),
    },
    required=frozenset({"language"}),
)

# Stage keys are sourced from the domain registry (KNOWN_STAGES) so the
# schema and the language-coverage / semantic-rule consumers all share
# a single source of truth. ``_extra`` is an ac-guard-specific escape
# hatch for raw pre-commit repos and is not a stage.
_CODE_CONFIG = Dict(
    fields={
        **dict.fromkeys(KNOWN_STAGES, _STAGE_BUCKET),
        "_extra": _EXTRA,
    }
)

_PRE_COMMIT_META = Dict(
    fields={
        "minimum_version": Str(),
        "default_install_hook_types": List(items=Str()),
        "default_language_version": DynDict(values=Str()),
    }
)

_BUILD_CONFIG = Dict(fields={"command": Str()})

_BEHAVIOR_CONFIG = Dict(fields=dict.fromkeys(("read", "write", "execute"), _OPERATION))

# Root schema
_ROOT = Dict(
    fields={
        "version": Int(enum=frozenset({1})),
        "project": _PROJECT_CONFIG,
        "rulesets": List(items=Str()),
        "languages": DynDict(
            values=_LANGUAGE_ENTRY,
            key_enum=frozenset(TYPE_EXTENSIONS),
        ),
        "behavior": _BEHAVIOR_CONFIG,
        "code": _CODE_CONFIG,
        "build": _BUILD_CONFIG,
        "output": _OUTPUT_CONFIG,
        "_pre_commit": _PRE_COMMIT_META,
    },
    required=frozenset({"version", "project"}),
)


# --- Public API ---


def validate_raw_config(
    data: dict[str, Any],
    *,
    source: str = "guard.yaml",
) -> None:
    """Validate a raw config dict against the guard.yaml schema.

    Performs structural checks (types, allowed keys, required fields)
    and semantic checks (enum values, regex validity, value ranges).
    Collects all issues and raises once.

    Args:
        data: Parsed YAML dict to validate.
        source: Label for error messages (file path or description).

    Raises:
        ConfigValidationError: If any validation issues are found.
    """
    validator = _Validator(source)
    validator.run(data)


# --- Internal implementation ---


class _Validator:
    """Accumulates validation issues and raises at the end."""

    def __init__(self, source: str) -> None:
        self._errors: list[ValidationIssue] = []
        self._source = source

    def _add(self, path: str, message: str, value: Any = None) -> None:
        self._errors.append(ValidationIssue(path, message, value))

    def _raise_if_errors(self) -> None:
        if self._errors:
            raise ConfigValidationError(self._errors)

    def run(self, data: dict[str, Any]) -> None:
        self._walk(data, _ROOT, "")
        self._raise_if_errors()

    def _walk(self, data: Any, node: SchemaNode, path: str) -> None:
        """Dispatch to type-specific checker based on node kind."""
        match node:
            case Str():
                self._check_str(data, node, path)
            case Int():
                self._check_int(data, node, path)
            case Bool():
                self._check_bool(data, path)
            case Dict():
                self._check_dict(data, node, path)
            case DynDict():
                self._check_dyndict(data, node, path)
            case List():
                self._check_list(data, node, path)

    # --- Scalar checkers ---
    # Each only handles its own type, eliminating invalid constraint combinations.

    def _check_str(self, data: Any, node: Str, path: str) -> None:
        if not isinstance(data, str):
            self._add(path, f"expected string, got {type(data).__name__}", data)
            return
        if node.non_empty and not data:
            self._add(path, "must be a non-empty string", data)
        if node.enum is not None and data not in node.enum:
            sorted_vals = sorted(node.enum)
            self._add(
                path,
                f"invalid value '{data}', must be one of: {sorted_vals}",
                data,
            )

    def _check_int(self, data: Any, node: Int, path: str) -> None:
        # Reject bool explicitly (bool is int subclass in Python)
        if isinstance(data, bool) or not isinstance(data, int):
            self._add(path, f"expected int, got {type(data).__name__}", data)
            return
        if node.enum is not None and data not in node.enum:
            sorted_vals = sorted(node.enum)
            self._add(
                path,
                f"invalid value {data}, must be one of: {sorted_vals}",
                data,
            )
        if node.min_value is not None:
            if node.min_exclusive and data <= node.min_value:
                self._add(
                    path,
                    f"must be > {node.min_value}, got {data}",
                    data,
                )
            elif not node.min_exclusive and data < node.min_value:
                self._add(
                    path,
                    f"must be >= {node.min_value}, got {data}",
                    data,
                )

    def _check_bool(self, data: Any, path: str) -> None:
        if not isinstance(data, bool):
            self._add(path, f"expected bool, got {type(data).__name__}", data)

    # --- Structure checkers ---
    # Dict: fixed keys with white-list and required checks
    # DynDict: arbitrary keys, only validate values
    # List: arbitrary length, validate each item

    def _check_dict(self, data: Any, node: Dict, path: str) -> None:
        if not isinstance(data, dict):
            self._add(
                path,
                f"expected mapping, got {type(data).__name__}",
                data,
            )
            return

        # Check unknown keys (unless passthrough allowed)
        if not node.allow_unknown:
            allowed_keys = frozenset(node.fields.keys())
            for key in data:
                if key not in allowed_keys:
                    child_path = f"{path}.{key}" if path else key
                    self._add(child_path, f"unknown key '{key}'", key)

        # Check required fields and recurse into present fields
        for name, child_node in node.fields.items():
            child_path = f"{path}.{name}" if path else name
            if name in node.required and name not in data:
                self._add(child_path, "required field missing")
            elif name in data:
                self._walk(data[name], child_node, child_path)

        # Special: validate regex pattern when regex=True
        if (
            node.check_regex
            and isinstance(data, dict)
            and data.get("regex") is True
            and isinstance(data.get("pattern"), str)
        ):
            try:
                re.compile(data["pattern"])
            except re.error as exc:
                pattern_path = f"{path}.pattern" if path else "pattern"
                self._add(
                    pattern_path,
                    f"invalid regex pattern: {exc}",
                    data["pattern"],
                )

    def _check_dyndict(self, data: Any, node: DynDict, path: str) -> None:
        if not isinstance(data, dict):
            self._add(
                path,
                f"expected mapping, got {type(data).__name__}",
                data,
            )
            return

        for key, value in data.items():
            child_path = f"{path}.{key}" if path else key
            if node.key_enum is not None and key not in node.key_enum:
                sorted_vals = sorted(node.key_enum)
                self._add(
                    child_path,
                    f"unknown key '{key}', must be one of: {sorted_vals}",
                    key,
                )
                continue  # skip value recursion to avoid cascading noise
            self._walk(value, node.values, child_path)

    def _check_list(self, data: Any, node: List, path: str) -> None:
        if not isinstance(data, list):
            self._add(
                path,
                f"expected list, got {type(data).__name__}",
                data,
            )
            return

        for i, item in enumerate(data):
            self._walk(item, node.items, f"{path}[{i}]")
