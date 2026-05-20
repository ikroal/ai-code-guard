"""AgentAdapter registry — closed-set built-in lookup.

Holds the immutable, eagerly-constructed mapping of built-in
:class:`AgentAdapter` instances and exposes name-based lookup helpers.

The set is closed: there is no registration / unregistration API and
no plugin-discovery mechanism. To add a new built-in adapter, add a
module under :mod:`ac_guard.adapters.builtins` and append the class to
the ``_BUILTINS`` tuple below. External extensibility (third-party
adapters via entry points) is intentionally out of scope; if it ever
becomes a real requirement it should be a separate, explicit design
proposal.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from ac_guard.adapters.builtins import (
    ClaudeCodeAdapter,
    CodexAdapter,
    CopilotAdapter,
    KiloCodeAdapter,
    OpenCodeAdapter,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ac_guard.adapters.base import AgentAdapter

__all__ = [
    "AdapterNotFoundError",
    "get_adapter",
    "list_adapters",
]


class AdapterNotFoundError(Exception):
    """Raised when ``get_adapter`` is called with an unknown name."""

    def __init__(self, name: str, available: list[str]) -> None:
        super().__init__(
            f"Agent adapter '{name}' not found. Available: {', '.join(available)}"
        )
        self.name = name
        self.available = available


_BUILTINS: Final[tuple[AgentAdapter, ...]] = (
    ClaudeCodeAdapter(),
    CodexAdapter(),
    OpenCodeAdapter(),
    CopilotAdapter(),
    KiloCodeAdapter(),
)

_REGISTRY: Final[Mapping[str, AgentAdapter]] = MappingProxyType(
    {adapter.name: adapter for adapter in _BUILTINS}
)


def get_adapter(name: str) -> AgentAdapter:
    """Retrieve a built-in AgentAdapter by name.

    Args:
        name: The adapter identifier (e.g., ``"claude-code"``).

    Returns:
        The built-in :class:`AgentAdapter` instance.

    Raises:
        AdapterNotFoundError: If no adapter is registered with that name.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        raise AdapterNotFoundError(name, list_adapters()) from None


def list_adapters() -> list[str]:
    """List all built-in adapter names.

    Returns:
        Sorted list of adapter identifiers.
    """
    return sorted(_REGISTRY)
