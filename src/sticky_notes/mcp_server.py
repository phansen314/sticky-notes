from __future__ import annotations

import argparse
import dataclasses
import sqlite3
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import Lifespan

from . import service
from .connection import DEFAULT_DB_PATH, get_connection, init_db
from .export import export_markdown


# ---- Serialization ----


def to_dict(obj: Any) -> Any:
    """Convert dataclasses (possibly nested) to plain dicts.

    Handles StrEnum → .value, tuples of dataclasses, and nested dataclasses.
    Does *not* use dataclasses.asdict() which recurses incorrectly for StrEnum.
    """
    if isinstance(obj, StrEnum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: to_dict(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
        }
    if isinstance(obj, (list, tuple)):
        return [to_dict(item) for item in obj]
    return obj


# ---- Helpers ----


def _conn(ctx: Context) -> sqlite3.Connection:
    return ctx.lifespan_context["conn"]


def _changes(
    clear_fields: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a changes dict from non-None keyword arguments.

    Fields listed in `clear_fields` are set to None explicitly, allowing
    callers to clear nullable fields like due_date or description.
    Only field names present in `kwargs` are accepted in `clear_fields`.
    """
    changes = {k: v for k, v in kwargs.items() if v is not None}
    if clear_fields:
        bad = [f for f in clear_fields if f not in kwargs]
        if bad:
            raise ToolError(f"unknown fields in clear_fields: {', '.join(bad)}")
        for field in clear_fields:
            changes[field] = None
    return changes


def _require(action: str, **params: Any) -> None:
    """Raise ToolError if any required parameter is None."""
    missing = [name for name, val in params.items() if val is None]
    if missing:
        raise ToolError(f"{', '.join(missing)} required for {action}")


# ---- Lifespan ----


async def _default_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    conn = get_connection(DEFAULT_DB_PATH)
    init_db(conn)
    try:
        yield {"conn": conn}
    finally:
        conn.close()


# ---- Server factory ----


def create_server(lifespan: Lifespan | None = None) -> FastMCP:
    if lifespan is None:
        lifespan = Lifespan(_default_lifespan)

    mcp = FastMCP(
        "Sticky Notes",
        lifespan=lifespan,
    )

    # ---- Board tool ----

    @mcp.tool()
    async def board(
        ctx: Context,
        action: str,
        board_id: int | None = None,
        name: str | None = None,
        archived: bool | None = None,
        include_archived: bool = False,
    ) -> dict | list | str:
        """Manage boards. Actions: create, get, list, update.

        - create: requires `name`
        - get: requires `board_id` or `name` (exactly one)
        - list: optional `include_archived`
        - update: requires `board_id`, optional `name`, `archived`
        """
        conn = _conn(ctx)
        try:
            match action:
                case "create":
                    _require("create", name=name)
                    return to_dict(service.create_board(conn, name))
                case "get":
                    if board_id is not None:
                        return to_dict(service.get_board(conn, board_id))
                    if name is not None:
                        return to_dict(service.get_board_by_name(conn, name))
                    raise ToolError("board_id or name required for get")
                case "list":
                    return to_dict(service.list_boards(conn, include_archived=include_archived))
                case "update":
                    _require("update", board_id=board_id)
                    changes = _changes(name=name, archived=archived)
                    if not changes:
                        raise ToolError("no fields to update")
                    return to_dict(service.update_board(conn, board_id, changes))
                case _:
                    raise ToolError(f"unknown action {action!r}")
        except (LookupError, sqlite3.IntegrityError) as exc:
            raise ToolError(str(exc)) from exc

    # ---- Column tool ----

    @mcp.tool()
    async def column(
        ctx: Context,
        action: str,
        board_id: int | None = None,
        column_id: int | None = None,
        name: str | None = None,
        position: int | None = None,
        archived: bool | None = None,
        include_archived: bool = False,
    ) -> dict | list | str:
        """Manage columns. Actions: create, list, update.

        - create: requires `board_id`, `name`, optional `position`
        - list: requires `board_id`, optional `include_archived`
        - update: requires `column_id`, optional `name`, `position`, `archived`
        """
        conn = _conn(ctx)
        try:
            match action:
                case "create":
                    _require("create", board_id=board_id, name=name)
                    return to_dict(
                        service.create_column(conn, board_id, name, position if position is not None else 0)
                    )
                case "list":
                    _require("list", board_id=board_id)
                    return to_dict(
                        service.list_columns(conn, board_id, include_archived=include_archived)
                    )
                case "update":
                    _require("update", column_id=column_id)
                    changes = _changes(name=name, position=position, archived=archived)
                    if not changes:
                        raise ToolError("no fields to update")
                    return to_dict(service.update_column(conn, column_id, changes))
                case _:
                    raise ToolError(f"unknown action {action!r}")
        except (LookupError, sqlite3.IntegrityError) as exc:
            raise ToolError(str(exc)) from exc

    # ---- Project tool ----

    @mcp.tool()
    async def project(
        ctx: Context,
        action: str,
        board_id: int | None = None,
        project_id: int | None = None,
        name: str | None = None,
        description: str | None = None,
        archived: bool | None = None,
        include_archived: bool = False,
        clear_fields: list[str] | None = None,
    ) -> dict | list | str:
        """Manage projects. Actions: create, get, list, update.

        - create: requires `board_id`, `name`, optional `description`
        - get: requires `project_id` (returns hydrated ProjectDetail)
        - list: requires `board_id`, optional `include_archived`
        - update: requires `project_id`, optional `name`, `description`, `archived`; use `clear_fields` to set nullable fields to null (e.g. `["description"]`)
        """
        conn = _conn(ctx)
        try:
            match action:
                case "create":
                    _require("create", board_id=board_id, name=name)
                    return to_dict(service.create_project(conn, board_id, name, description))
                case "get":
                    _require("get", project_id=project_id)
                    return to_dict(service.get_project_detail(conn, project_id))
                case "list":
                    _require("list", board_id=board_id)
                    return to_dict(
                        service.list_projects(conn, board_id, include_archived=include_archived)
                    )
                case "update":
                    _require("update", project_id=project_id)
                    changes = _changes(
                        clear_fields=clear_fields,
                        name=name, description=description, archived=archived,
                    )
                    if not changes:
                        raise ToolError("no fields to update")
                    return to_dict(service.update_project(conn, project_id, changes))
                case _:
                    raise ToolError(f"unknown action {action!r}")
        except (LookupError, sqlite3.IntegrityError) as exc:
            raise ToolError(str(exc)) from exc

    # ---- Task tool ----

    @mcp.tool()
    async def task(
        ctx: Context,
        action: str,
        board_id: int | None = None,
        task_id: int | None = None,
        title: str | None = None,
        column_id: int | None = None,
        project_id: int | None = None,
        description: str | None = None,
        priority: int | None = None,
        due_date: int | None = None,
        position: int | None = None,
        start_date: int | None = None,
        finish_date: int | None = None,
        archived: bool | None = None,
        include_archived: bool = False,
        clear_fields: list[str] | None = None,
    ) -> dict | list | str:
        """Manage tasks. Actions: create, get, list, update, move.

        - create: requires `board_id`, `title`, `column_id`; optional `project_id`, `description`, `priority`, `due_date`, `position`, `start_date`, `finish_date`
        - get: requires `task_id` (returns hydrated TaskDetail)
        - list: requires `board_id`, optional `include_archived` (returns TaskRef[])
        - update: requires `task_id`; optional field kwargs build a changes dict; use `clear_fields` to set nullable fields to null (e.g. `["due_date", "description"]`)
        - move: requires `task_id`, `column_id`, optional `position`
        - move_to_board: requires `task_id`, `board_id` (target), `column_id` (target); optional `project_id`. Creates a copy on the target board and archives the original. Fails if task has dependencies.
        """
        conn = _conn(ctx)
        try:
            match action:
                case "create":
                    _require("create", board_id=board_id, title=title, column_id=column_id)
                    kwargs: dict[str, Any] = {}
                    if project_id is not None:
                        kwargs["project_id"] = project_id
                    if description is not None:
                        kwargs["description"] = description
                    if priority is not None:
                        kwargs["priority"] = priority
                    if due_date is not None:
                        kwargs["due_date"] = due_date
                    if position is not None:
                        kwargs["position"] = position
                    if start_date is not None:
                        kwargs["start_date"] = start_date
                    if finish_date is not None:
                        kwargs["finish_date"] = finish_date
                    return to_dict(
                        service.create_task(conn, board_id, title, column_id, **kwargs)
                    )
                case "get":
                    _require("get", task_id=task_id)
                    return to_dict(service.get_task_detail(conn, task_id))
                case "list":
                    _require("list", board_id=board_id)
                    return to_dict(
                        service.list_task_refs(conn, board_id, include_archived=include_archived)
                    )
                case "update":
                    _require("update", task_id=task_id)
                    changes = _changes(
                        clear_fields=clear_fields,
                        title=title,
                        description=description,
                        column_id=column_id,
                        project_id=project_id,
                        priority=priority,
                        due_date=due_date,
                        position=position,
                        archived=archived,
                        start_date=start_date,
                        finish_date=finish_date,
                    )
                    if not changes:
                        raise ToolError("no fields to update")
                    return to_dict(service.update_task(conn, task_id, changes, source="mcp"))
                case "move":
                    _require("move", task_id=task_id, column_id=column_id)
                    return to_dict(
                        service.move_task(
                            conn, task_id, column_id, position if position is not None else 0, source="mcp"
                        )
                    )
                case "move_to_board":
                    _require("move_to_board", task_id=task_id, board_id=board_id, column_id=column_id)
                    return to_dict(
                        service.move_task_to_board(
                            conn, task_id, board_id, column_id,
                            project_id=project_id, source="mcp",
                        )
                    )
                case _:
                    raise ToolError(f"unknown action {action!r}")
        except (LookupError, ValueError, sqlite3.IntegrityError) as exc:
            raise ToolError(str(exc)) from exc

    # ---- Dependency tool ----

    @mcp.tool()
    async def dependency(
        ctx: Context,
        action: str,
        task_id: int | None = None,
        depends_on_id: int | None = None,
    ) -> str:
        """Manage task dependencies. Actions: add, remove.

        - add: requires `task_id`, `depends_on_id`
        - remove: requires `task_id`, `depends_on_id`
        """
        conn = _conn(ctx)
        try:
            match action:
                case "add":
                    _require("add", task_id=task_id, depends_on_id=depends_on_id)
                    service.add_dependency(conn, task_id, depends_on_id)
                    return "ok"
                case "remove":
                    _require("remove", task_id=task_id, depends_on_id=depends_on_id)
                    service.remove_dependency(conn, task_id, depends_on_id)
                    return "ok"
                case _:
                    raise ToolError(f"unknown action {action!r}")
        except (LookupError, sqlite3.IntegrityError) as exc:
            raise ToolError(str(exc)) from exc

    # ---- Task history tool ----

    @mcp.tool()
    async def task_history(
        ctx: Context,
        action: str,
        task_id: int | None = None,
    ) -> list | str:
        """View task change history. Actions: list.

        - list: requires `task_id`
        """
        conn = _conn(ctx)
        try:
            match action:
                case "list":
                    _require("list", task_id=task_id)
                    return to_dict(service.list_task_history(conn, task_id))
                case _:
                    raise ToolError(f"unknown action {action!r}")
        except (LookupError, sqlite3.IntegrityError) as exc:
            raise ToolError(str(exc)) from exc

    # ---- Export tool ----

    @mcp.tool(name="export")
    async def export_tool(ctx: Context) -> str:
        """Export the full database to Markdown. Returns a Markdown report with all
        non-archived boards, columns, projects, tasks, and a Mermaid dependency graph."""
        conn = _conn(ctx)
        return export_markdown(conn)

    return mcp


def _get_server() -> FastMCP:
    """Lazy singleton for `fastmcp run` compatibility.

    Avoids creating a FastMCP instance at import time, which would
    bake in the production lifespan during test collection.
    """
    global _lazy_server
    if _lazy_server is None:
        _lazy_server = create_server()
    return _lazy_server


_lazy_server: FastMCP | None = None


def __getattr__(name: str) -> Any:
    """Module-level __getattr__ to lazily create the server instance."""
    if name == "mcp":
        return _get_server()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sticky Notes MCP Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8741)
    args = parser.parse_args()

    _get_server().run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
