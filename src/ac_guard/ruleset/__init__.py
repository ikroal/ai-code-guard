"""Ruleset management for AI Code Guard.

Provides URL parsing, git-based fetch, local cache management,
and validation for external rulesets.
"""

from ac_guard.ruleset.cache import clear_cache, get_cache_dir, list_cached
from ac_guard.ruleset.exceptions import (
    RulesetError,
    RulesetFetchError,
    RulesetURLError,
    RulesetValidationError,
)
from ac_guard.ruleset.fetcher import fetch_ruleset, validate_ruleset_dir
from ac_guard.ruleset.models import CACHE_DIR, RulesetRef
from ac_guard.ruleset.parser import parse_ruleset_url

__all__ = [
    "CACHE_DIR",
    "RulesetError",
    "RulesetFetchError",
    "RulesetRef",
    "RulesetURLError",
    "RulesetValidationError",
    "clear_cache",
    "fetch_ruleset",
    "get_cache_dir",
    "list_cached",
    "parse_ruleset_url",
    "validate_ruleset_dir",
]
