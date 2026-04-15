"""Generator module for AI Guard.

Consumes ResolvedConfig and generates all static artifacts (rule docs,
hook scripts, tool configs, pre-commit config, policy cache, git hooks).
"""

from ai_guard.generator.core import (
    create_state,
    delete_artifacts,
    read_state,
    replace_managed_block,
    wrap_with_managed_block,
    write_artifacts,
    write_state,
)
from ai_guard.generator.exceptions import (
    AdapterNotRegisteredError,
    ArtifactWriteError,
    GeneratorError,
    GitDirectoryNotFoundError,
)
from ai_guard.generator.models import (
    STATE_FILE,
    FileSpec,
    GeneratedState,
)

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
    # Core functions
    "create_state",
    "delete_artifacts",
    "read_state",
    "write_state",
    "write_artifacts",
    "replace_managed_block",
    "wrap_with_managed_block",
]
