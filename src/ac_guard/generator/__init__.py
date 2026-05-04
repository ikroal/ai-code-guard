"""Generator module for AI Code Guard.

Consumes ResolvedConfig and produces all static artifacts (rule docs,
hook scripts, tool configs, pre-commit config, policy cache, git hooks).

``generate_all`` is the single orchestration entry-point for
``install`` / ``update``.  The seven per-G primitives are
module-private (test via deep import from ``core``).
"""

from ac_guard.domain import FileSpec  # Shared DTO, re-exported for callers
from ac_guard.generator.core import (
    create_installation,
    delete_artifacts,
    delete_installation,
    generate_all,
    read_installation,
    write_artifacts,
    write_installation,
)
from ac_guard.generator.exceptions import (
    ArtifactWriteError,
    GeneratorError,
)
from ac_guard.generator.models import Installation, installation_path

__all__ = [
    # Schema
    "FileSpec",
    "Installation",
    # Exceptions
    "GeneratorError",
    "ArtifactWriteError",
    # Orchestration
    "generate_all",
    "write_artifacts",
    # Installation lifecycle
    "read_installation",
    "write_installation",
    "create_installation",
    "delete_installation",
    "installation_path",
    # Cleanup
    "delete_artifacts",
]
