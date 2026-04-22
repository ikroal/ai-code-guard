"""Tests for FileChannel."""

from __future__ import annotations

from pathlib import Path

import pytest

from ac_guard.reporter.channels.base import ChannelError, get_channel
from ac_guard.reporter.channels.file import FileChannel


class TestFileChannel:
    """FileChannel writes payloads to a given path."""

    def test_name(self) -> None:
        assert FileChannel.name == "file"

    def test_registered(self) -> None:
        assert get_channel("file") is FileChannel

    def test_output_writes_utf8(self, tmp_path: Path) -> None:
        target = tmp_path / "report.md"
        FileChannel(target).output("# 标题\n\ncontent")
        assert target.read_text(encoding="utf-8") == "# 标题\n\ncontent"

    def test_output_format_agnostic(self, tmp_path: Path) -> None:
        md_target = tmp_path / "report.md"
        json_target = tmp_path / "report.json"
        FileChannel(md_target).output("# Markdown")
        FileChannel(json_target).output('{"key": "value"}')
        assert md_target.read_text(encoding="utf-8") == "# Markdown"
        assert json_target.read_text(encoding="utf-8") == '{"key": "value"}'

    def test_output_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "report.md"
        target.write_text("old content", encoding="utf-8")
        FileChannel(target).output("new content")
        assert target.read_text(encoding="utf-8") == "new content"

    def test_output_raises_on_missing_parent(self, tmp_path: Path) -> None:
        """Parent directory must exist; FileChannel does not create it."""
        target = tmp_path / "does" / "not" / "exist" / "report.md"
        with pytest.raises(ChannelError, match="Failed to write"):
            FileChannel(target).output("content")
