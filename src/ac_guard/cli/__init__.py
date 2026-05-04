"""CLI for AI Code Guard.

The CLI is the shell-facing boundary that translates user-typed intents
into orchestrated calls into the domain modules. Its sole public symbol
is the Typer ``app`` consumed by the ``ac-guard`` console_script.

Submodules (``cli.init`` / ``cli.install`` / ``cli.run`` / ``cli.status``
/ ``cli.show`` / ``cli.ruleset`` / ``cli.presets``) are private to the
package; tests that need their internals deep-import directly from
those paths (mirrors the ``ruleset`` / ``generator`` precedent).
"""

from ac_guard.cli.main import app

__all__ = ["app"]
