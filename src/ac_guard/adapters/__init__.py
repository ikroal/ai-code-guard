"""Agent adapters package for AI Code Guard.

Public surface:

- :class:`AgentAdapter` — abstract base class for vendor-specific
  artifact generation strategies.
- :class:`AgentCapabilities` — capability declaration dataclass.
- :func:`get_adapter` / :func:`list_adapters` — name-based lookup
  against the closed set of built-in adapters.
- :class:`AdapterNotFoundError` — raised by ``get_adapter`` on miss.

The five built-ins (constructed once as an immutable mapping at import
time):

- ``claude-code`` (can_block=True, can_ask=True)
- ``opencode`` (can_block=True, can_ask=True)
- ``copilot`` (can_block=False, can_ask=False)
- ``kilocode`` (can_block=False, can_ask=False)
"""

from ac_guard.adapters.base import AgentAdapter, AgentCapabilities
from ac_guard.adapters.registry import (
    AdapterNotFoundError,
    get_adapter,
    list_adapters,
)

__all__ = [
    "AdapterNotFoundError",
    "AgentAdapter",
    "AgentCapabilities",
    "get_adapter",
    "list_adapters",
]
