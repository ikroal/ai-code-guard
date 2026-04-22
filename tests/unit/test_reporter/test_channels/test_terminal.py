"""Tests for TerminalChannel."""

from __future__ import annotations

import io
import sys

from ac_guard.reporter.channels.base import get_channel
from ac_guard.reporter.channels.terminal import TerminalChannel


class TestTerminalChannel:
    """TerminalChannel writes to a configurable text stream."""

    def test_name(self) -> None:
        assert TerminalChannel.name == "terminal"

    def test_registered(self) -> None:
        assert get_channel("terminal") is TerminalChannel

    def test_default_stream_is_stdout(self) -> None:
        ch = TerminalChannel()
        assert ch.stream is sys.stdout

    def test_output_writes_to_custom_stream(self) -> None:
        buf = io.StringIO()
        TerminalChannel(stream=buf).output("hello")
        # print adds a trailing newline
        assert buf.getvalue() == "hello\n"

    def test_output_format_agnostic(self) -> None:
        """Terminal channel accepts any string — markdown / JSON / plain."""
        buf = io.StringIO()
        ch = TerminalChannel(stream=buf)
        ch.output("## Markdown heading")
        ch.output('{"key": "value"}')
        ch.output("plain text")
        assert "## Markdown heading\n" in buf.getvalue()
        assert '{"key": "value"}\n' in buf.getvalue()
        assert "plain text\n" in buf.getvalue()

    def test_output_multiline_preserved(self) -> None:
        buf = io.StringIO()
        TerminalChannel(stream=buf).output("line1\nline2\nline3")
        assert buf.getvalue() == "line1\nline2\nline3\n"
