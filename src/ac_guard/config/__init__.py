"""Configuration system for AI Code Guard."""

from ac_guard.config.exceptions import (
    ConfigError,
    ConfigFileNotFoundError,
    ConfigSyntaxError,
    ConfigValidationError,
    ConfigWarning,
    ValidationIssue,
)
from ac_guard.config.loader import RawConfig, load_config
from ac_guard.config.merger import resolve_config
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
from ac_guard.config.validator import validate_raw_config

__all__ = [
    # Exceptions
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigSyntaxError",
    "ConfigValidationError",
    "ConfigWarning",
    "ValidationIssue",
    # Loader
    "load_config",
    "RawConfig",
    # Merger
    "resolve_config",
    # Validator
    "validate_raw_config",
    # Models
    "Rule",
    "OperationRules",
    "BehaviorConfig",
    "CheckItem",
    "CodeConfig",
    "LanguageTools",
    "AuditConfig",
    "PrReportConfig",
    "OutputConfig",
    "ResolvedConfig",
]
