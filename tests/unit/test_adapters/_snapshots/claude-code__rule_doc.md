


## Behavior Constraints

The following rules define what operations are permitted, blocked, or require approval.

### Read Operations

**Forbidden** (blocked):
- `file:.env*` — environment files contain secrets

**Require Approval** (ask user):
- `file:**/credentials.json` — contains credentials, confirm before reading

**Allowed** (permitted):
- `file:**/*.py`

### Write Operations

**Forbidden** (blocked):
- `file:.git/**` — repo internals must not be edited

**Require Approval** (ask user):
- `file:pyproject.toml` — dependency change — confirm intent

### Execute Operations

**Forbidden** (blocked):
- `^rm\s+-rf\s+/` — filesystem destruction

**Require Approval** (ask user):
- `shell:git push --force*` — rewrites remote history

**Allowed** (permitted):
- `shell:pytest *`
