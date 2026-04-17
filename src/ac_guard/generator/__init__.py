"""Generator module for AI Code Guard.

Consumes ResolvedConfig and generates all static artifacts (rule docs,
hook scripts, tool configs, pre-commit config, policy cache, git hooks).

G primitives:
- G1: generate_rule_docs - Agent-specific rule documents
- G2: generate_hook_files - Agent-specific Hook scripts
- G3-G6: Agent-agnostic artifacts (WP1.3c)
- G7: write_artifacts - Write all artifacts to disk
"""

from ac_guard.generator.core import (
    create_state,
    delete_artifacts,
    generate_git_hooks,
    generate_hook_files,
    generate_policy_cache,
    generate_precommit_config,
    generate_rule_docs,
    generate_tool_configs,
    read_state,
    replace_managed_block,
    wrap_with_managed_block,
    write_artifacts,
    write_state,
)
from ac_guard.generator.exceptions import (
    AdapterNotRegisteredError,
    ArtifactWriteError,
    GeneratorError,
    GitDirectoryNotFoundError,
)
from ac_guard.generator.models import STATE_FILE, GeneratedState
from ac_guard.shared.types import FileSpec  # Shared type

__all__ = [
    # Exceptions
    "GeneratorError",
    "ArtifactWriteError",
    "GitDirectoryNotFoundError",
    "AdapterNotRegisteredError",
    # Models
    "FileSpec",
    "GeneratedState",
    "STATE_FILE",
    # G1/G2 primitives
    "generate_rule_docs",
    "generate_hook_files",
    # G3-G6 primitives
    "generate_policy_cache",
    "generate_git_hooks",
    "generate_tool_configs",
    "generate_precommit_config",
    # Core functions
    "create_state",
    "delete_artifacts",
    "read_state",
    "write_state",
    "write_artifacts",
    "replace_managed_block",
    "wrap_with_managed_block",
]
