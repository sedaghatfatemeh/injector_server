# Beads task tracking

For application startup instructions, see [راهنمای فارسی اجرای پروژه روی ویندوز](local-setup.fa.md). Beads is not required to run the application.

Beads 1.3.4 is initialized for this repository with the `injector` issue prefix
and an embedded Dolt database. It needs no separate database server and is a
development tool, not an application runtime dependency.

## Windows commands

Run these from the repository root:

```powershell
./scripts/bd.cmd version
./scripts/bd.cmd ready
./scripts/bd.cmd list
./scripts/bd.cmd show <id>
./scripts/bd.cmd update <id> --claim
./scripts/bd.cmd close <id> --reason "Implemented and verified"
./scripts/bd.cmd create "Describe the work" --type task --priority 2
./scripts/bd.cmd dep add <dependent-id> <blocker-id>
./scripts/bd.cmd export -o .beads/issues.jsonl
```

The wrapper uses `.local/beads/bd.exe`, falling back to `bd.exe` on PATH.
The `.cmd` wrapper works with Windows PowerShell's default script policy.
You can also invoke the binary directly: `./.local/beads/bd.exe ready`.

The original five milestone epics and their tasks were imported from
[`implementation-plan.md`](implementation-plan.md). `.beads/plan-map.json`
maps plan keys to generated issue IDs; tasks retain their plan keys as labels.
Imported implementation tasks start open because existing code still needs
verification against each task's acceptance criteria. Only the Beads setup
task is closed after setup verification.

## Installation on another Windows x64 checkout

Download `beads_1.3.4_windows_amd64.zip` and `checksums.txt` from the
[official release](https://github.com/gastownhall/beads/releases/tag/v1.3.4).
Compare `Get-FileHash <archive> -Algorithm SHA256` against its entry in
`checksums.txt` before extracting. The checksum verified for this setup was:

```text
e66e7b66c0d1ac6a878951462edddb4a177532aff3fc22989daac115feaaef11
```

Extract the archive into `.local/beads/`, or put `bd.exe` on PATH. Other
platforms can install the matching CLI using the
[official installation guide](https://github.com/gastownhall/beads/blob/main/docs/getting-started/installation.md).

For a fresh checkout without a local database, initialize and import the
reviewable issue snapshot:

```powershell
./scripts/bd.cmd init --prefix injector --non-interactive --skip-hooks --skip-agents
./scripts/bd.cmd import -i .beads/issues.jsonl
./scripts/bd.cmd ready
```

Do not reinitialize a populated database. Hooks are skipped; root `AGENTS.md`
provides the project workflow without changing global IDE settings.

## Storage, Git, and recovery

Commit `.beads/config.yaml`, `metadata.json`, `.gitignore`, `README.md`,
`plan-map.json`, and the refreshed `issues.jsonl` snapshot with relevant changes.
The live database at `.beads/embeddeddolt/`, CLI files under `.local/`, locks,
and credentials remain ignored. The Dolt database is the source of truth;
JSONL is an issue interchange snapshot and does not preserve database history.
Auto-export is enabled but throttled, so export explicitly before reviewing
or committing task changes. No automatic Git staging is enabled.

No shared Dolt remote or automatic backup is configured. Full database
recovery requires a Dolt-native backup, for example:

```powershell
./scripts/bd.cmd backup init C:/backups/injector-beads
./scripts/bd.cmd backup sync
```

Choose an actual backup destination before running those commands. Use
`bd dolt push` / `bd dolt pull` only after a shared remote has been configured;
ordinary Git commits alone do not sync the live database.

## Approved customer-access increment (2026-11-18)

The additional CUST-EPIC and CUST-001 through CUST-007 track administrator-provisioned customer login and the organization-scoped read-only device panel. CUST-000 tracks scope/documentation alignment only; its closure does not indicate working customer access. See the approved increment in [the implementation plan](implementation-plan.md). Existing closed staff tasks retain their original acceptance history; new customer tasks depend on them without reopening them. UI-005 final console acceptance also depends on CUST-007. Plan keys and generated Beads IDs remain in .beads/plan-map.json; use Beads for current status and export the issue snapshot after changes.
