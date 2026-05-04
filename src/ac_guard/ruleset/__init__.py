"""Ruleset management for AI Code Guard.

Materialises external ruleset references declared in ``guard.yaml``
into project-local copies and exposes primitives for parsing,
fetching, listing, content access, and lifecycle management of those
copies.
"""

from ac_guard.ruleset.cache import (
    clear_cache,
    get_cache_dir,
    get_ruleset_dir,
    list_cached,
    load_ruleset_config,
    read_meta,
)
from ac_guard.ruleset.exceptions import (
    RulesetError,
    RulesetFetchError,
    RulesetURLError,
    RulesetValidationError,
)
from ac_guard.ruleset.fetcher import fetch_ruleset
from ac_guard.ruleset.models import RulesetRef
from ac_guard.ruleset.parser import parse_ruleset_url

__all__ = [
    "RulesetError",
    "RulesetFetchError",
    "RulesetRef",
    "RulesetURLError",
    "RulesetValidationError",
    "clear_cache",
    "fetch_ruleset",
    "get_cache_dir",
    "get_ruleset_dir",
    "list_cached",
    "load_ruleset_config",
    "parse_ruleset_url",
    "read_meta",
]
