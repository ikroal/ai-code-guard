
## Behavior Constraints

> **Warning**: GitHub Copilot does not support runtime interception.
> The rules below are soft constraints in the instructions document.
> Enforcement relies on Git Hooks and manual code review.

The following rules define recommended constraints for AI operations.

### Read Operations

**Forbidden** (recommended deny):
- `file:.env*` — environment files contain secrets

**Require Approval** (recommended deny - no ask capability):
- `file:**/credentials.json` — contains credentials, confirm before reading

**Allowed** (permitted):
- `file:**/*.py`

### Write Operations

**Forbidden** (recommended deny):
- `file:.git/**` — repo internals must not be edited

**Require Approval** (recommended deny - no ask capability):
- `file:pyproject.toml` — dependency change — confirm intent

### Execute Operations

**Forbidden** (recommended deny):
- `^rm\s+-rf\s+/` — filesystem destruction

**Require Approval** (recommended deny - no ask capability):
- `shell:git push --force*` — rewrites remote history

**Allowed** (permitted):
- `shell:pytest *`
