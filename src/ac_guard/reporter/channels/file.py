"""FileChannel — write rendered payloads to a local file."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ac_guard.reporter.channels.base import (
    ChannelError,
    ReportChannel,
    register_channel,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["FileChannel"]


@register_channel
class FileChannel(ReportChannel):
    """Write an already-rendered string payload to a local file.

    This channel is format-agnostic: hand it any string (markdown, JSON,
    plain text) and it writes the bytes to ``path``. The caller chooses
    both the rendering function and the destination extension::

        FileChannel(Path("report.md")).output(format_markdown(outcome, "en"))
        FileChannel(Path("report.json")).output(format_json(outcome))
    """

    name = "file"

    def __init__(self, path: Path) -> None:
        """Store the destination path.

        Args:
            path: Destination file path. Parent directories are not created;
                callers must ensure they exist.
        """
        self.path = path

    def output(self, payload: str) -> None:
        """Write ``payload`` to :attr:`path`, replacing any existing file.

        Args:
            payload: The rendered string to write.

        Raises:
            ChannelError: If writing to :attr:`path` fails (parent directory
                missing, permission denied, etc.).
        """
        try:
            self.path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            raise ChannelError(f"Failed to write report to {self.path}: {exc}") from exc
