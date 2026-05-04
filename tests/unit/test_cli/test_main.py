"""Smoke tests for CLI entry point."""

from typer.testing import CliRunner

from ac_guard import __version__
from ac_guard.cli.main import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "guard" in result.output.lower()
