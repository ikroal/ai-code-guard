"""AI Guard CLI entry point."""

from typing import Optional

import typer

from ai_guard import __version__

app = typer.Typer(
    name="guard",
    help="AI Guard - Guardian system for AI coding agents.",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    show_version: Optional[bool] = typer.Option(
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
