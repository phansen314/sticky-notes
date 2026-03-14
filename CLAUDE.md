# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A local todo/kanban app (`todo` CLI) with three interfaces: TUI (Textual), MCP server (FastMCP), and SQLite storage. Both TUI and MCP share the same database and service layer. This is an early-stage project — repository, service, TUI, and MCP layers are not yet built.

## Architecture

```
TUI event handlers ──┐
                     ├──▶ Service ──▶ Repository ──▶ Connection ──▶ SQLite
MCP tool functions ──┘
```

**Data hierarchy:** Board → Column → Task (and Board → Project → Task). Columns are board-scoped and represent kanban workflow stages. No data is ever deleted — use `archived` flags instead.

## Key Design Conventions

- **Separate pre-insert and persisted types** — `NewTask` (no `id`/`created_at`) vs `Task` (full row). Never use `None` as a stand-in for "not yet assigned."
- **Ref vs Detail service models** — `TaskRef` carries relationship IDs (cheap, for lists). `TaskDetail` carries hydrated objects (expensive, for detail views).
- **All dataclasses are frozen** — immutability throughout. Changes produce new instances via DB.
- **Defaults on pre-insert dataclasses** — optional/defaultable fields on `New*` types carry defaults directly. No factory layer needed.
- **Service models inherit from domain models** — `TaskRef(Task)`, `TaskDetail(Task)`, etc. Child fields use defaults to satisfy dataclass field ordering. Access task fields directly (`ref.title`), not via composition.
- **Mappers are plain functions** — explicit conversion at each layer boundary (row→model, model→ref, ref→detail). Models are pure data containers with no methods — conversion logic stays in `mappers.py`, not as classmethods. Accept the boilerplate to keep separation clean.
- **Transaction context manager** — service layer controls transaction boundaries. Repository functions receive a connection and never commit/rollback.
- **Timestamps as Unix epoch integers** — formatting happens at the edges only.
- **Task numbers** — formatted as `task-{id:04d}` in the application layer, derived from autoincrement ID.
- **DB path** — `~/.local/share/sticky-notes/sticky-notes.db` (XDG-compliant).
- **WAL journal mode** — enables concurrent reads from TUI and MCP.

## Python

- Python 3.12+ (uses `type` statement for type aliases, `str | None` union syntax)
- No external dependencies yet beyond stdlib, Textual, and FastMCP
