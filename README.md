![CI](https://github.com/ikroal/ai-code-guard/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-alpha-orange)

# AI Guard

Guardrails for AI coding agents. One `guard.yaml` constrains behavior and enforces code quality across Claude Code, Cursor, OpenCode, Copilot, and KiloCode.

A single config file replaces per-agent rule documents, scattered hook scripts, and manual pre-commit setup.

- **Runtime interception** — agent hooks block dangerous operations (force push, secret access, config tampering) before they execute
- **Code quality gates** — format, lint, naming, and custom checks at commit and push time
- **Anti-bypass protection** — the agent cannot modify its own constraints, disable hooks, or skip checks
- **5 agents, 1 config** — `guard.yaml` generates agent-specific rule docs, hook scripts, pre-commit config, and policy files

## Installation

```bash
pip install ai-guard
```

## Quick Start

```bash
guard init --language python          # create guard.yaml
guard install --agent claude-code     # generate rules + hooks
guard check                           # run quality checks
guard ruleset fetch <url>#v1.0        # fetch shared ruleset
```

## Supported Agents

| Agent | Runtime Hook | Code Quality | Rule Document |
|-------|:---:|:---:|---|
| Claude Code | deny + ask | yes | `CLAUDE.md` |
| Cursor | deny | yes | `.cursor/rules/behavior.mdc` |
| OpenCode | deny + ask | yes | `AGENTS.md` |
| GitHub Copilot | — | yes | `.github/copilot-instructions.md` |
| KiloCode | — | yes | `.kilocode/rules/behavior.md` |

Agents with runtime hooks intercept operations before execution. Agents without hooks receive behavior rules as soft constraints in their rule documents. All agents get pre-commit quality gates.

## Configuration

```yaml
behavior:
  write:
    forbidden:
      - pattern: "file:.git/**"
      - pattern: "file:**/.env"
    require_approval:
      - pattern: "file:guard.yaml"
  execute:
    forbidden:
      - pattern: "shell:git push --force*"
      - pattern: "shell:git commit --no-verify*"

code:
  commit:
    format: true
    naming: true
  push:
    lint: true
```

Patterns use `{scheme}:{glob}` format — `file:`, `shell:`, `mcp:`, `web:`. Add `regex: true` for regex matching.

Rules are evaluated in priority order: **forbidden** (deny) > **require_approval** (ask user) > **allow** > default allow.

See [guard.yaml reference](design/AI_GUARD_SYSTEM_DESIGN.md) for full schema.

## Commands

| Command | Description |
|---------|-------------|
| `guard init` | Generate `guard.yaml` from presets |
| `guard install --agent <name>` | Generate rules, hooks, and configs |
| `guard update` | Regenerate after config changes |
| `guard uninstall` | Remove generated artifacts |
| `guard check` | Run commit-stage checks |
| `guard verify` | Run push-stage validation |
| `guard run <name>` | Run a single check |
| `guard gate run --stage <s>` | Git hook entry point |
| `guard status` | Installation state and drift detection |
| `guard doctor` | Environment diagnostics |
| `guard agents` | Agent capability matrix |
| `guard ruleset fetch` | Fetch a ruleset from a git repository |
| `guard ruleset list` | List cached rulesets |
| `guard ruleset cache clear` | Clear the ruleset cache |

## How It Works

`guard install` reads `guard.yaml` and generates all artifacts at once — rule documents, hook scripts, `.pre-commit-config.yaml`, and `.ai-guard/policy.json`. No config parsing happens at runtime.

When the agent runs, its hook script loads the pre-built policy and matches each operation against the rules. Forbidden operations are blocked. Operations requiring approval prompt the user. Everything else is allowed. Every decision is logged to `.ai-guard/audit.jsonl`.

At commit and push time, pre-commit hooks run format, lint, naming, and custom checks. The agent cannot skip these because `git commit --no-verify` is itself a forbidden pattern.

## Roadmap

- [x] **Phase 1** — Config + Generator + CLI (8 commands)
- [x] **Phase 2** — Enforcer + runtime behavior interception
- [x] **Phase 3** — Checker + Reporter + code quality gates
- [ ] **Phase 4** — Ruleset fetch, caching, and management
- [ ] **Phase 5** — PR report posting and CI/CD integration

## Development

```bash
pip install -e ".[dev]"
pytest                    # 692 tests
ruff check .
```

## License

[MIT](LICENSE)
