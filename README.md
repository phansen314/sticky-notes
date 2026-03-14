# sticky-notes

A local todo/kanban app with three interfaces:

- **TUI** (Textual) — human interaction
- **MCP server** (FastMCP) — Claude interaction
- **SQLite** — persistent storage

Both TUI and MCP share the same database and service layer.

## Architecture

```
TUI event handlers ──┐
                     ├──▶ Service ──▶ Repository ──▶ Connection ──▶ SQLite
MCP tool functions ──┘
```

## Data Model

**Hierarchy:** Board → Column → Task (and Board → Project → Task)

To generate an ER diagram from the schema:

```sh
python scripts/generate_erd.py
```

This parses `schema.sql` and outputs a Mermaid diagram to stdout. Pipe to a file if needed:

```sh
python scripts/generate_erd.py > erd.mermaid
```

## Requirements

- Python 3.12+
- [Textual](https://textual.textualize.io/) (TUI)
- [FastMCP](https://github.com/jlowin/fastmcp) (MCP server)

## Data Storage

Database path: `~/.local/share/sticky-notes/sticky-notes.db` (XDG-compliant)
