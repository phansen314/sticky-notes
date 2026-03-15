from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import Lifespan

from sticky_notes.connection import get_connection, init_db
from sticky_notes.mcp_server import create_server, to_dict
from sticky_notes.models import Board, TaskField, TaskHistory

pytestmark = pytest.mark.anyio


# ---- Fixtures ----


@pytest.fixture
def mcp_server(db_path: Path) -> FastMCP:
    async def test_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        conn = get_connection(db_path)
        init_db(conn)
        try:
            yield {"conn": conn}
        finally:
            conn.close()

    return create_server(lifespan=Lifespan(test_lifespan))


@pytest.fixture
async def client(mcp_server: FastMCP):
    async with Client(mcp_server) as c:
        yield c


# ---- Helper ----


def _text(result) -> Any:
    """Extract text content from a CallToolResult and parse as JSON if possible."""
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def _call(client: Client, tool: str, args: dict) -> Any:
    """Call a tool and return parsed result. Raises ToolError on is_error."""
    return _text(await client.call_tool(tool, args))


async def _call_err(client: Client, tool: str, args: dict) -> str:
    """Call a tool expecting an error. Returns the error message."""
    result = await client.call_tool(tool, args, raise_on_error=False)
    assert result.is_error, f"Expected error but got success: {result.content}"
    return result.content[0].text


# ---- to_dict tests ----


class TestToDict:
    def test_plain_scalars(self) -> None:
        assert to_dict(42) == 42
        assert to_dict("hello") == "hello"
        assert to_dict(None) is None

    def test_str_enum(self) -> None:
        assert to_dict(TaskField.TITLE) == "title"

    def test_dataclass(self) -> None:
        b = Board(id=1, name="dev", archived=False, created_at=1000)
        result = to_dict(b)
        assert result == {"id": 1, "name": "dev", "archived": False, "created_at": 1000}

    def test_tuple_of_dataclasses(self) -> None:
        boards = (
            Board(id=1, name="a", archived=False, created_at=1),
            Board(id=2, name="b", archived=True, created_at=2),
        )
        result = to_dict(boards)
        assert len(result) == 2
        assert result[0]["name"] == "a"
        assert result[1]["archived"] is True

    def test_nested_dataclass(self) -> None:
        h = TaskHistory(
            id=1, task_id=10, field=TaskField.TITLE,
            old_value="old", new_value="new", source="cli", changed_at=999,
        )
        result = to_dict(h)
        assert result["field"] == "title"
        assert result["old_value"] == "old"


# ---- Board tool ----


async def test_board_create_and_get(client: Client) -> None:
    result = await _call(client, "board", {"action": "create", "name": "Dev Board"})
    assert result["name"] == "Dev Board"
    board_id = result["id"]

    result = await _call(client, "board", {"action": "get", "board_id": board_id})
    assert result["id"] == board_id
    assert result["name"] == "Dev Board"


async def test_board_get_by_name(client: Client) -> None:
    await _call(client, "board", {"action": "create", "name": "Alpha"})
    result = await _call(client, "board", {"action": "get", "name": "Alpha"})
    assert result["name"] == "Alpha"


async def test_board_list(client: Client) -> None:
    await _call(client, "board", {"action": "create", "name": "B1"})
    await _call(client, "board", {"action": "create", "name": "B2"})
    result = await _call(client, "board", {"action": "list"})
    assert len(result) == 2


async def test_board_update(client: Client) -> None:
    created = await _call(client, "board", {"action": "create", "name": "Old"})
    updated = await _call(client, "board", {
        "action": "update", "board_id": created["id"], "name": "New",
    })
    assert updated["name"] == "New"


async def test_board_get_nonexistent(client: Client) -> None:
    err = await _call_err(client, "board", {"action": "get", "board_id": 999})
    assert "not found" in err


async def test_board_get_missing_params(client: Client) -> None:
    err = await _call_err(client, "board", {"action": "get"})
    assert "required" in err


async def test_board_create_missing_name(client: Client) -> None:
    err = await _call_err(client, "board", {"action": "create"})
    assert "name" in err and "required" in err


async def test_board_create_duplicate(client: Client) -> None:
    await _call(client, "board", {"action": "create", "name": "Dup"})
    err = await _call_err(client, "board", {"action": "create", "name": "Dup"})
    assert "UNIQUE" in err or "unique" in err.lower()


async def test_board_unknown_action(client: Client) -> None:
    err = await _call_err(client, "board", {"action": "delete"})
    assert "unknown action" in err


async def test_board_update_no_fields(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    err = await _call_err(client, "board", {"action": "update", "board_id": b["id"]})
    assert "no fields" in err


async def test_board_update_missing_id(client: Client) -> None:
    err = await _call_err(client, "board", {"action": "update", "name": "X"})
    assert "board_id" in err and "required" in err


# ---- Column tool ----


async def test_column_crud(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    bid = b["id"]

    col = await _call(client, "column", {
        "action": "create", "board_id": bid, "name": "Todo",
    })
    assert col["name"] == "Todo"

    cols = await _call(client, "column", {"action": "list", "board_id": bid})
    assert len(cols) == 1

    updated = await _call(client, "column", {
        "action": "update", "column_id": col["id"], "name": "Done",
    })
    assert updated["name"] == "Done"


async def test_column_create_missing_params(client: Client) -> None:
    err = await _call_err(client, "column", {"action": "create", "name": "X"})
    assert "board_id" in err and "required" in err


async def test_column_list_missing_board(client: Client) -> None:
    err = await _call_err(client, "column", {"action": "list"})
    assert "board_id" in err and "required" in err


async def test_column_update_missing_id(client: Client) -> None:
    err = await _call_err(client, "column", {"action": "update", "name": "X"})
    assert "column_id" in err and "required" in err


async def test_column_update_no_fields(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {"action": "create", "board_id": b["id"], "name": "C"})
    err = await _call_err(client, "column", {"action": "update", "column_id": col["id"]})
    assert "no fields" in err


# ---- Project tool ----


async def test_project_crud(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    bid = b["id"]

    p = await _call(client, "project", {
        "action": "create", "board_id": bid, "name": "Alpha", "description": "desc",
    })
    assert p["name"] == "Alpha"
    assert p["description"] == "desc"

    detail = await _call(client, "project", {"action": "get", "project_id": p["id"]})
    assert detail["name"] == "Alpha"
    assert "tasks" in detail

    projects = await _call(client, "project", {"action": "list", "board_id": bid})
    assert len(projects) == 1

    updated = await _call(client, "project", {
        "action": "update", "project_id": p["id"], "name": "Beta",
    })
    assert updated["name"] == "Beta"


async def test_project_create_missing_params(client: Client) -> None:
    err = await _call_err(client, "project", {"action": "create", "name": "X"})
    assert "board_id" in err


async def test_project_get_missing_id(client: Client) -> None:
    err = await _call_err(client, "project", {"action": "get"})
    assert "project_id" in err


async def test_project_list_missing_board(client: Client) -> None:
    err = await _call_err(client, "project", {"action": "list"})
    assert "board_id" in err


# ---- Task tool ----


async def test_task_full_lifecycle(client: Client) -> None:
    # Setup: board + column
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {
        "action": "create", "board_id": b["id"], "name": "Todo",
    })
    col2 = await _call(client, "column", {
        "action": "create", "board_id": b["id"], "name": "Done",
    })

    # Create task
    t = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "Fix bug",
        "column_id": col["id"], "priority": 3,
    })
    assert t["title"] == "Fix bug"
    assert t["priority"] == 3

    # Get task detail
    detail = await _call(client, "task", {"action": "get", "task_id": t["id"]})
    assert detail["title"] == "Fix bug"
    assert detail["column"]["name"] == "Todo"

    # List task refs
    refs = await _call(client, "task", {"action": "list", "board_id": b["id"]})
    assert len(refs) == 1
    assert refs[0]["title"] == "Fix bug"

    # Update task
    updated = await _call(client, "task", {
        "action": "update", "task_id": t["id"], "title": "Fix critical bug",
    })
    assert updated["title"] == "Fix critical bug"

    # Move task
    moved = await _call(client, "task", {
        "action": "move", "task_id": t["id"], "column_id": col2["id"],
    })
    assert moved["column_id"] == col2["id"]

    # Verify history was recorded
    history = await _call(client, "task_history", {
        "action": "list", "task_id": t["id"],
    })
    assert len(history) >= 1
    fields_changed = {h["field"] for h in history}
    assert "title" in fields_changed


async def test_task_create_uses_service_defaults(client: Client) -> None:
    """Create without optional params should use service defaults, not duplicate them."""
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {"action": "create", "board_id": b["id"], "name": "C"})
    t = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T", "column_id": col["id"],
    })
    assert t["priority"] == 1
    assert t["position"] == 0


async def test_task_create_missing_params(client: Client) -> None:
    err = await _call_err(client, "task", {"action": "create", "title": "X"})
    assert "board_id" in err or "column_id" in err


async def test_task_get_missing_id(client: Client) -> None:
    err = await _call_err(client, "task", {"action": "get"})
    assert "task_id" in err


async def test_task_list_missing_board(client: Client) -> None:
    err = await _call_err(client, "task", {"action": "list"})
    assert "board_id" in err


async def test_task_update_missing_id(client: Client) -> None:
    err = await _call_err(client, "task", {"action": "update", "title": "X"})
    assert "task_id" in err


async def test_task_update_no_fields(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {"action": "create", "board_id": b["id"], "name": "C"})
    t = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T", "column_id": col["id"],
    })
    err = await _call_err(client, "task", {"action": "update", "task_id": t["id"]})
    assert "no fields" in err


async def test_task_move_missing_column(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {"action": "create", "board_id": b["id"], "name": "C"})
    t = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T", "column_id": col["id"],
    })
    err = await _call_err(client, "task", {"action": "move", "task_id": t["id"]})
    assert "column_id" in err


async def test_task_clear_fields(client: Client) -> None:
    """clear_fields should set nullable fields to None."""
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {"action": "create", "board_id": b["id"], "name": "C"})
    t = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T",
        "column_id": col["id"], "description": "will be cleared",
        "due_date": 1700000000,
    })
    assert t["description"] == "will be cleared"
    assert t["due_date"] == 1700000000

    updated = await _call(client, "task", {
        "action": "update", "task_id": t["id"],
        "clear_fields": ["description", "due_date"],
    })
    assert updated["description"] is None
    assert updated["due_date"] is None


async def test_task_clear_fields_rejects_unknown(client: Client) -> None:
    """clear_fields with a non-updatable field name should error."""
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {"action": "create", "board_id": b["id"], "name": "C"})
    t = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T", "column_id": col["id"],
    })
    err = await _call_err(client, "task", {
        "action": "update", "task_id": t["id"],
        "clear_fields": ["id"],
    })
    assert "unknown fields" in err


# ---- Dependency tool ----


async def test_dependency_add_remove(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {
        "action": "create", "board_id": b["id"], "name": "Todo",
    })
    t1 = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T1", "column_id": col["id"],
    })
    t2 = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T2", "column_id": col["id"],
    })

    result = await _call(client, "dependency", {
        "action": "add", "task_id": t2["id"], "depends_on_id": t1["id"],
    })
    assert result == "ok"

    # Verify via task detail
    detail = await _call(client, "task", {"action": "get", "task_id": t2["id"]})
    assert t1["id"] in detail["blocked_by_ids"]

    # Remove
    result = await _call(client, "dependency", {
        "action": "remove", "task_id": t2["id"], "depends_on_id": t1["id"],
    })
    assert result == "ok"


async def test_dependency_add_missing_params(client: Client) -> None:
    err = await _call_err(client, "dependency", {"action": "add", "task_id": 1})
    assert "depends_on_id" in err


async def test_dependency_self_ref(client: Client) -> None:
    b = await _call(client, "board", {"action": "create", "name": "B"})
    col = await _call(client, "column", {"action": "create", "board_id": b["id"], "name": "C"})
    t = await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "T", "column_id": col["id"],
    })
    err = await _call_err(client, "dependency", {
        "action": "add", "task_id": t["id"], "depends_on_id": t["id"],
    })
    assert err  # IntegrityError caught and re-raised as ToolError


# ---- Task history tool ----


async def test_task_history_missing_id(client: Client) -> None:
    err = await _call_err(client, "task_history", {"action": "list"})
    assert "task_id" in err


async def test_task_history_unknown_action(client: Client) -> None:
    err = await _call_err(client, "task_history", {"action": "delete"})
    assert "unknown action" in err


# ---- Export tool ----


async def test_export_with_data(client: Client) -> None:
    """Export should include board, column, and task data."""
    b = await _call(client, "board", {"action": "create", "name": "Export Board"})
    col = await _call(client, "column", {
        "action": "create", "board_id": b["id"], "name": "Backlog",
    })
    await _call(client, "task", {
        "action": "create", "board_id": b["id"], "title": "Ship it",
        "column_id": col["id"],
    })

    result = await _call(client, "export", {})
    assert "# Sticky Notes Export" in result
    assert "Export Board" in result
    assert "Ship it" in result


async def test_export_empty(client: Client) -> None:
    """Export on an empty database should return the header but no board headings."""
    result = await _call(client, "export", {})
    assert "# Sticky Notes Export" in result
    assert "## " not in result


# ---- Error signaling ----


async def test_errors_set_is_error_flag(client: Client) -> None:
    """Errors should use MCP's is_error mechanism, not plain strings."""
    result = await client.call_tool("board", {"action": "get", "board_id": 999}, raise_on_error=False)
    assert result.is_error is True


async def test_errors_raise_with_raise_on_error(client: Client) -> None:
    """With raise_on_error=True (default), errors should raise ToolError."""
    with pytest.raises(ToolError):
        await client.call_tool("board", {"action": "get", "board_id": 999})
