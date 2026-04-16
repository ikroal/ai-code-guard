"""AI Guard CLI entry point."""

from pathlib import Path
from typing import Annotated

import typer

from ai_guard import __version__
from ai_guard.cli.init import init_command

app = typer.Typer(
    name="guard",
    help="AI Guard - Guardian system for AI coding agents.",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    show_version: bool | None = typer.Option(
        None, "--version", "-V", help="Print version and exit."
    ),
) -> None:
    """AI Guard - Guardian system for AI coding agents."""
    if show_version:
        typer.echo(f"ai-guard {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def version() -> None:
    """Print AI Guard version."""
    typer.echo(f"ai-guard {__version__}")


@app.command()
def init(
    language: Annotated[
        str,
        typer.Option(
            "--language",
            "-l",
            help="Project language (python, typescript, go, rust, etc.)",
        ),
    ],
    preset: Annotated[
        str,
        typer.Option(
            "--preset",
            "-p",
            help="Configuration preset: minimal, standard, or strict",
        ),
    ] = "standard",
    ruleset: Annotated[
        list[str] | None,
        typer.Option(
            "--ruleset",
            "-r",
            help="Ruleset references to include (can be repeated)",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing guard.yaml",
        ),
    ] = False,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output file path",
        ),
    ] = Path("guard.yaml"),
) -> None:
    """Initialize a new guard.yaml configuration file.

    Creates a configuration file based on the selected preset, customized
    with the provided language and optional ruleset references.
    """
    init_command(
        language=language,
        preset=preset,
        rulesets=ruleset or [],
        force=force,
        output=output,
    )
