"""AI Code Guard CLI entry point."""

from pathlib import Path
from typing import Annotated

import typer

from ac_guard import __version__
from ac_guard.cli.check import (
    check_command,
    gate_run_command,
    run_command,
    verify_command,
)
from ac_guard.cli.init import init_command
from ac_guard.cli.install import install_command, uninstall_command, update_command
from ac_guard.cli.ruleset import (
    ruleset_cache_clear_command,
    ruleset_fetch_command,
    ruleset_list_command,
    ruleset_show_command,
)
from ac_guard.cli.status import agents_command, doctor_command, status_command
from ac_guard.cli.validation import validation_list_command, validation_report_command

app = typer.Typer(
    name="ac-guard",
    help=(
        "AI Code Guard (ac-guard) — Guardian system for AI coding agents.\n"
        "\n"
        "Install: pip install ac-guard\n"
        "Docs:    https://github.com/ikroal/ai-code-guard"
    ),
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    show_version: bool | None = typer.Option(
        None, "--version", "-V", help="Print version and exit."
    ),
) -> None:
    """AI Code Guard (ac-guard) — Guardian system for AI coding agents."""
    if show_version:
        typer.echo(f"ac-guard {__version__} — AI Code Guard")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def version() -> None:
    """Print AI Code Guard version."""
    typer.echo(f"ac-guard {__version__} — AI Code Guard")


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


@app.command()
def install(
    agent: Annotated[
        str | None,
        typer.Option(
            "--agent",
            "-a",
            help="Comma-separated agent names (e.g., claude-code,cursor)",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to guard.yaml",
        ),
    ] = Path("guard.yaml"),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing tool config files from rulesets",
        ),
    ] = False,
) -> None:
    """Install AI Code Guard artifacts for specified agents.

    Without --agent, lists available agents. With --agent, generates
    rule documents, Hook scripts, tool configs, and Git hooks.
    """
    agents = [a.strip() for a in agent.split(",") if a.strip()] if agent else []
    project_root = config.parent.resolve()
    install_command(
        agents=agents, project_root=project_root, config_path=config, force=force
    )


@app.command()
def update(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to guard.yaml",
        ),
    ] = Path("guard.yaml"),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing tool config files from rulesets",
        ),
    ] = False,
) -> None:
    """Re-generate all artifacts for installed agents.

    Reads the current installation state and regenerates all
    artifacts based on the latest guard.yaml configuration.
    """
    project_root = config.parent.resolve()
    update_command(project_root=project_root, config_path=config, force=force)


@app.command()
def uninstall(
    keep_config: Annotated[
        bool,
        typer.Option(
            "--keep-config",
            help="Keep guard.yaml after uninstall",
        ),
    ] = False,
) -> None:
    """Remove all AI Code Guard artifacts.

    Deletes generated files tracked in .ac-guard/state.json.
    Use --keep-config to preserve guard.yaml.
    """
    project_root = Path.cwd()
    uninstall_command(project_root=project_root, keep_config=keep_config)


@app.command()
def status(
    rules: Annotated[
        bool,
        typer.Option(
            "--rules",
            help="Display active rule list with sources",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to guard.yaml",
        ),
    ] = Path("guard.yaml"),
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: text or json",
        ),
    ] = "text",
) -> None:
    """Show installation status, drift detection, and artifact integrity."""
    project_root = config.parent.resolve()
    status_command(
        project_root=project_root,
        config_path=config,
        show_rules=rules,
        output_format=output_format,
    )


@app.command()
def doctor(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to guard.yaml",
        ),
    ] = Path("guard.yaml"),
) -> None:
    """Run environment diagnostics and check system health."""
    project_root = config.parent.resolve()
    doctor_command(project_root=project_root, config_path=config)


@app.command()
def agents() -> None:
    """Display agent capability matrix and installation status."""
    project_root = Path.cwd()
    agents_command(project_root=project_root)


@app.command()
def check(
    files: Annotated[
        list[str] | None,
        typer.Option(
            "--files",
            help="Explicit file paths to check (default: staged files)",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to guard.yaml"),
    ] = Path("guard.yaml"),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text or json"),
    ] = "text",
) -> None:
    """Run commit-stage quality checks."""
    check_command(files=files or [], config_path=config, output_format=output_format)


@app.command()
def verify(
    skip_build: Annotated[
        bool,
        typer.Option("--skip-build", help="Skip the build step"),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to guard.yaml"),
    ] = Path("guard.yaml"),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text or json"),
    ] = "text",
) -> None:
    """Run full push-stage validation (includes commit checks)."""
    verify_command(
        skip_build=skip_build, config_path=config, output_format=output_format
    )


@app.command(name="run")
def run_single(
    name: Annotated[str, typer.Argument(help="Check name to run")],
    stage: Annotated[
        str,
        typer.Option("--stage", "-s", help="Check stage (commit or push)"),
    ] = "commit",
    files: Annotated[
        list[str] | None,
        typer.Option("--files", help="Explicit file paths to check"),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to guard.yaml"),
    ] = Path("guard.yaml"),
) -> None:
    """Run a single named check item."""
    run_command(name=name, stage=stage, files=files or [], config_path=config)


# gate subcommand group
gate_app = typer.Typer(name="gate", help="Git Hook entry points.")


@gate_app.command(name="run")
def gate_run(
    stage: Annotated[
        str,
        typer.Option("--stage", "-s", help="Check stage (commit or push)"),
    ] = "commit",
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to guard.yaml"),
    ] = Path("guard.yaml"),
) -> None:
    """Internal entry point for Git hooks."""
    gate_run_command(stage=stage, config_path=config)


app.add_typer(gate_app)

# ruleset subcommand group
ruleset_app = typer.Typer(name="ruleset", help="Manage external rulesets.")
cache_app = typer.Typer(name="cache", help="Manage ruleset cache.")


@ruleset_app.command(name="fetch")
def ruleset_fetch(
    url: Annotated[
        str,
        typer.Argument(help="Git URL of the ruleset (use #version for pinning)"),
    ],
    project_root: Annotated[
        Path,
        typer.Option("--project-root", "-p", help="Project root directory"),
    ] = Path("."),
) -> None:
    """Fetch or update a ruleset from a Git repository."""
    ruleset_fetch_command(url=url, project_root=project_root.resolve())


@ruleset_app.command(name="list")
def ruleset_list(
    project_root: Annotated[
        Path,
        typer.Option("--project-root", "-p", help="Project root directory"),
    ] = Path("."),
) -> None:
    """List cached rulesets."""
    ruleset_list_command(project_root=project_root.resolve())


@ruleset_app.command(name="show")
def ruleset_show(
    name: Annotated[
        str,
        typer.Argument(help="Ruleset name to display"),
    ],
    project_root: Annotated[
        Path,
        typer.Option("--project-root", "-p", help="Project root directory"),
    ] = Path("."),
) -> None:
    """Show details of a cached ruleset."""
    ruleset_show_command(name=name, project_root=project_root.resolve())


@cache_app.command(name="clear")
def cache_clear(
    project_root: Annotated[
        Path,
        typer.Option("--project-root", "-p", help="Project root directory"),
    ] = Path("."),
) -> None:
    """Remove all cached rulesets."""
    ruleset_cache_clear_command(project_root=project_root.resolve())


ruleset_app.add_typer(cache_app)
app.add_typer(ruleset_app)

# validation subcommand group
validation_app = typer.Typer(name="validation", help="Inspect configured checks.")


@validation_app.command(name="list")
def validation_list(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to guard.yaml"),
    ] = Path("guard.yaml"),
) -> None:
    """List all configured checks by stage."""
    validation_list_command(config_path=config)


@validation_app.command(name="report")
def validation_report(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to guard.yaml"),
    ] = Path("guard.yaml"),
) -> None:
    """Generate a formatted check configuration report."""
    validation_report_command(config_path=config)


app.add_typer(validation_app)
