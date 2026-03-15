# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A local todo/kanban app (`todo` CLI) with three interfaces: CLI (argparse), TUI (Textual), and MCP server (FastMCP), all backed by SQLite storage. The CLI is the primary interface today. Repository, service, CLI, mappers, and export layers are fully implemented. TUI and MCP layers are not yet built.

## Architecture

```
CLI commands ────────┐
TUI event handlers ──┤
                     ├──▶ Service ──▶ Repository ──▶ Connection ──▶ SQLite
MCP tool functions ──┘
```

**Data hierarchy:** Board → Column → Task (and Board → Project → Task). Columns are board-scoped and represent kanban workflow stages. No data is ever deleted — use `archived` flags instead.

## Project Structure

```
src/sticky_notes/
  __main__.py      # entry point (todo command)
  cli.py           # argparse CLI — commands, output formatting
  service.py       # business logic, transaction boundaries
  repository.py    # raw SQL queries, one function per operation
  connection.py    # SQLite connection factory, schema init
  models.py        # domain dataclasses (New*, persisted)
  service_models.py# Ref/Detail dataclasses for service layer
  mappers.py       # row→model, model→ref, ref→detail converters
  export.py        # full-database Markdown + Mermaid export
  schema.sql       # DDL

tests/
  conftest.py      # fixtures (fresh DB, seeded board/columns/tasks)
  helpers.py       # raw SQL insert helpers for test setup
  test_cli.py      # CLI integration tests
  test_connection.py
  test_export.py
  test_mappers.py
  test_repository.py
  test_service.py
```

## CLI

Entry point: `todo = "sticky_notes.__main__:main"`.

**Active board:** persisted at `~/.local/share/sticky-notes/active-board`. CLI resolves board from `--board`/`-b` flag, falling back to this file. Set via `todo board create` or `todo board use`.

**Command structure:**
- Top-level task commands: `add`, `ls`, `show`, `edit`, `mv`, `done`, `rm`, `log`
- Subcommand groups: `board`, `col`, `project`, `dep`, `export`

## Key Design Conventions

- **Separate pre-insert and persisted types** — `NewTask` (no `id`/`created_at`) vs `Task` (full row). Never use `None` as a stand-in for "not yet assigned."
- **Ref vs Detail service models** — `TaskRef` carries relationship IDs (cheap, for lists). `TaskDetail` carries hydrated objects (expensive, for detail views).
- **All dataclasses are frozen** — immutability throughout. Changes produce new instances via DB.
- **Defaults on pre-insert dataclasses** — optional/defaultable fields on `New*` types carry defaults directly. No factory layer needed.
- **Service models inherit from domain models** — `TaskRef(Task)`, `TaskDetail(TaskRef)`, etc. Inheritance chain: `Task → TaskRef → TaskDetail`. Child fields use defaults to satisfy dataclass field ordering. Access task fields directly (`ref.title`), not via composition.
- **Mappers are plain functions** — explicit conversion at each layer boundary (row→model, model→ref, ref→detail). Models are pure data containers with no methods — conversion logic stays in `mappers.py`, not as classmethods. Accept the boilerplate to keep separation clean.
- **`shallow_fields()` helper** — extracts parent dataclass fields as a dict for constructing derived types (Ref, Detail). Lives in `mappers.py`.
- **Repository update allowlists** — each entity has a `_*_UPDATABLE` frozenset guarding which fields can be passed to update functions.
- **Task history / audit trail** — `_record_changes()` in the service layer auto-records `TaskHistory` entries for changed fields. `TaskField` enum defines trackable fields.
- **Transaction context manager** — service layer controls transaction boundaries. Repository functions receive a connection and never commit/rollback. On rollback failure, `raise exc from rollback_exc` — the original error is primary, rollback failure is attached as `__cause__`. This is intentional.
- **Timestamps as Unix epoch integers** — formatting happens at the edges only.
- **Task numbers** — formatted as `task-{id:04d}` in the application layer, derived from autoincrement ID.
- **Active board file** — persisted at `~/.local/share/sticky-notes/active-board`. CLI resolves board from `--board` flag or this file.
- **Export** — `export.py` renders the full database to Markdown with Mermaid dependency graphs.
- **DB path** — `~/.local/share/sticky-notes/sticky-notes.db` (XDG-compliant).
- **WAL journal mode** — enables concurrent reads from TUI and MCP.

## Testing

- **pytest** with `pytest-cov`; fixtures in `conftest.py`, raw SQL insert helpers in `tests/helpers.py`
- Fresh in-memory DB per test — no cross-test pollution
- Test files cover all layers: connection, repository, service, mappers, export, CLI

## Python

- Python 3.12+ (uses `type` statement for type aliases, `str | None` union syntax)
- Build system: hatchling
- Dependencies: textual, fastmcp
- Dev dependencies: pytest, pytest-cov
