# Beads project state

This repository uses Beads 1.3.4 with an embedded Dolt database and the `injector` issue prefix.

Run `./scripts/bd.cmd ready` from the repository root. See [development workflow](../docs/development-workflow.md) for setup, task commands, snapshots, and backups.

- `plan-map.json` maps the implementation plan to generated issue IDs.
- `issues.jsonl` is a reviewable issue snapshot; refresh it with `./scripts/bd.cmd export -o .beads/issues.jsonl`.
- `embeddeddolt/` is the live database and is ignored by Git.
- No shared remote or automatic backup is configured.
