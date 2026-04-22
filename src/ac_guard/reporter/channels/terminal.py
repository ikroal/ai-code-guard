"""TerminalChannel — print rendered payloads to a text stream."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from ac_guard.reporter.channels.base import ReportChannel, register_channel

if TYPE_CHECKING:
    from typing import TextIO

__all__ = ["TerminalChannel"]


@register_channel
class TerminalChannel(ReportChannel):
    """Print an already-rendered string payload to a text stream.

    This channel is format-agnostic: hand it any string (produced by
    :func:`~ac_guard.reporter.formatting.format_terminal`, ``format_json``,
    plain text, etc.) and it writes to ``stream`` (default ``sys.stdout``).

    Typical use::

        TerminalChannel().output(format_terminal(outcome, "verbose", "en"))

    Or with a captured stream for testing / logging::

        buf = io.StringIO()
        TerminalChannel(stream=buf).output(format_json(outcome))
    """

    name = "terminal"

    def __init__(self, stream: TextIO | None = None) -> None:
        """Store the output stream.

        Args:
            stream: Destination text stream. Defaults to :data:`sys.stdout`.
        """
        self.stream = stream if stream is not None else sys.stdout

    def output(self, payload: str) -> None:
        """Write ``payload`` to the configured stream, followed by a newline.

        Args:
            payload: The rendered string to print.
        """
        print(payload, file=self.stream)
