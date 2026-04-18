"""Integration tests for hook wiring in service.py task mutations (task 158)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from stx import service
from stx.hooks import HookEvent, HookTiming
from stx.service import _determine_task_events
from stx.models import HookRejectionError


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _ws_status(conn: sqlite3.Connection, ws_name: str = "ws", st_name: str = "todo"):
    ws = service.create_workspace(conn, ws_name)
    st = service.create_status(conn, ws.id, st_name)
    return ws, st


def _task(conn: sqlite3.Connection, ws_id: int, status_id: int, title: str = "task A"):
    return service.create_task(conn, ws_id, title, status_id)


# ---------------------------------------------------------------------------
# _determine_task_events unit tests
# ---------------------------------------------------------------------------

class TestDetermineTaskEvents:
    def test_status_change_gives_moved(self) -> None:
        events = _determine_task_events({"status_id": {"old": 1, "new": 2}})
        assert events == [HookEvent.TASK_MOVED]

    def test_done_true_gives_done(self) -> None:
        events = _determine_task_events({"done": {"old": False, "new": True}})
        assert events == [HookEvent.TASK_DONE]

    def test_done_false_gives_undone(self) -> None:
        events = _determine_task_events({"done": {"old": True, "new": False}})
        assert events == [HookEvent.TASK_UNDONE]

    def test_group_set_gives_assigned(self) -> None:
        events = _determine_task_events({"group_id": {"old": None, "new": 5}})
        assert events == [HookEvent.TASK_ASSIGNED]

    def test_group_cleared_gives_unassigned(self) -> None:
        events = _determine_task_events({"group_id": {"old": 5, "new": None}})
        assert events == [HookEvent.TASK_UNASSIGNED]

    def test_title_change_gives_updated(self) -> None:
        events = _determine_task_events({"title": {"old": "a", "new": "b"}})
        assert events == [HookEvent.TASK_UPDATED]

    def test_status_and_title_gives_moved_and_updated(self) -> None:
        events = _determine_task_events({
            "status_id": {"old": 1, "new": 2},
            "title": {"old": "a", "new": "b"},
        })
        assert HookEvent.TASK_MOVED in events
        assert HookEvent.TASK_UPDATED in events

    def test_empty_changes_returns_empty(self) -> None:
        assert _determine_task_events({}) == []


# ---------------------------------------------------------------------------
# create_task hooks
# ---------------------------------------------------------------------------

class TestCreateTaskHooks:
    def test_pre_hook_fires_with_proposed(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        calls = []

        def fake_fire(event, timing, **kwargs):
            calls.append((event, timing, kwargs))

        with patch("stx.service.fire_hooks", side_effect=fake_fire):
            service.create_task(conn, ws.id, "mytask", st.id)

        pre = [(e, t, k) for e, t, k in calls if t == HookTiming.PRE]
        assert len(pre) == 1
        event, timing, kwargs = pre[0]
        assert event == HookEvent.TASK_CREATED
        assert kwargs["proposed"]["title"] == "mytask"
        assert kwargs["entity"] is None

    def test_post_hook_fires_with_entity(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        post_calls = []

        def fake_fire(event, timing, **kwargs):
            if timing == HookTiming.POST:
                post_calls.append(kwargs)

        with patch("stx.service.fire_hooks", side_effect=fake_fire):
            task = service.create_task(conn, ws.id, "mytask", st.id)

        assert len(post_calls) == 1
        entity = post_calls[0]["entity"]
        assert entity is not None
        assert entity.id == task.id
        assert entity.title == "mytask"

    def test_pre_hook_rejection_blocks_create(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hooks_toml = tmp_path / "hooks.toml"
        hooks_toml.write_text(
            '[[hooks]]\nevent = "task.created"\ntiming = "pre"\ncommand = "exit 1"\n'
        )
        monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)
        ws, st = _ws_status(conn)
        with pytest.raises(HookRejectionError):
            service.create_task(conn, ws.id, "blocked", st.id)
        # task must not exist
        assert service.list_tasks(conn, ws.id) == ()


# ---------------------------------------------------------------------------
# update_task hooks — event selection
# ---------------------------------------------------------------------------

class TestUpdateTaskHooks:
    def test_status_change_fires_moved(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        st2 = service.create_status(conn, ws.id, "done")
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append((e, t))):
            service.update_task(conn, task.id, {"status_id": st2.id}, "test")
        events = [e for e, _ in fired]
        assert HookEvent.TASK_MOVED in events

    def test_done_true_fires_task_done(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append((e, t))):
            service.update_task(conn, task.id, {"done": True}, "test")
        events = [e for e, _ in fired]
        assert HookEvent.TASK_DONE in events

    def test_done_false_fires_task_undone(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        service.update_task(conn, task.id, {"done": True}, "test")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append((e, t))):
            service.update_task(conn, task.id, {"done": False}, "test")
        events = [e for e, _ in fired]
        assert HookEvent.TASK_UNDONE in events

    def test_title_change_fires_updated(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append((e, t))):
            service.update_task(conn, task.id, {"title": "new title"}, "test")
        events = [e for e, _ in fired]
        assert HookEvent.TASK_UPDATED in events

    def test_terminal_status_fires_moved_and_done_post(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        terminal_st = service.create_status(conn, ws.id, "done")
        service.update_status(conn, terminal_st.id, {"is_terminal": True})
        task = _task(conn, ws.id, st.id)
        fired_post = []
        def fake_fire(event, timing, **kw):
            if timing == HookTiming.POST:
                fired_post.append(event)
        with patch("stx.service.fire_hooks", side_effect=fake_fire):
            service.update_task(conn, task.id, {"status_id": terminal_st.id}, "test")
        assert HookEvent.TASK_MOVED in fired_post
        assert HookEvent.TASK_DONE in fired_post

    def test_pre_hook_rejection_blocks_update(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hooks_toml = tmp_path / "hooks.toml"
        hooks_toml.write_text(
            '[[hooks]]\nevent = "task.updated"\ntiming = "pre"\ncommand = "exit 1"\n'
        )
        monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        with pytest.raises(HookRejectionError):
            service.update_task(conn, task.id, {"title": "blocked"}, "test")
        assert service.get_task(conn, task.id).title == "task A"


# ---------------------------------------------------------------------------
# archive_task hooks
# ---------------------------------------------------------------------------

class TestArchiveTaskHooks:
    def test_pre_and_post_fire(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append((e, t))):
            service.archive_task(conn, task.id, source="test")
        events_by_timing: dict = {}
        for e, t in fired:
            events_by_timing.setdefault(t, []).append(e)
        assert HookEvent.TASK_ARCHIVED in events_by_timing.get(HookTiming.PRE, [])
        assert HookEvent.TASK_ARCHIVED in events_by_timing.get(HookTiming.POST, [])

    def test_pre_rejection_blocks_archive(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hooks_toml = tmp_path / "hooks.toml"
        hooks_toml.write_text(
            '[[hooks]]\nevent = "task.archived"\ntiming = "pre"\ncommand = "exit 1"\n'
        )
        monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        with pytest.raises(HookRejectionError):
            service.archive_task(conn, task.id, source="test")
        assert not service.get_task(conn, task.id).archived


# ---------------------------------------------------------------------------
# move_task_to_workspace hooks
# ---------------------------------------------------------------------------

class TestTransferTaskHooks:
    def test_transferred_event_with_workspace_refs(
        self, conn: sqlite3.Connection
    ) -> None:
        ws1, st1 = _ws_status(conn, "src", "todo")
        ws2 = service.create_workspace(conn, "tgt")
        st2 = service.create_status(conn, ws2.id, "backlog")
        task = _task(conn, ws1.id, st1.id)
        post_kwargs = {}
        def fake_fire(event, timing, **kw):
            if event == HookEvent.TASK_TRANSFERRED and timing == HookTiming.POST:
                post_kwargs.update(kw)
        with patch("stx.service.fire_hooks", side_effect=fake_fire):
            service.move_task_to_workspace(conn, task.id, ws2.id, st2.id, source="test")
        assert post_kwargs["source_workspace"] == {"id": ws1.id, "name": "src"}
        assert post_kwargs["target_workspace"] == {"id": ws2.id, "name": "tgt"}
        assert post_kwargs["changes"]["workspace_id"]["old"] == ws1.id
        assert post_kwargs["changes"]["workspace_id"]["new"] == ws2.id


# ---------------------------------------------------------------------------
# set_task_meta / remove_task_meta / replace_task_metadata hooks
# ---------------------------------------------------------------------------

class TestMetaHooks:
    def test_set_meta_fires_pre_and_post(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append((e, t, kw))):
            service.set_task_meta(conn, task.id, "tag", "urgent")
        pre = [(e, t, k) for e, t, k in fired if t == HookTiming.PRE]
        post = [(e, t, k) for e, t, k in fired if t == HookTiming.POST]
        assert len(pre) == 1 and pre[0][0] == HookEvent.TASK_META_SET
        assert pre[0][2]["meta_key"] == "tag"
        assert pre[0][2]["meta_value"] == "urgent"
        assert len(post) == 1 and post[0][0] == HookEvent.TASK_META_SET

    def test_set_meta_no_hook_when_unchanged(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        service.set_task_meta(conn, task.id, "tag", "v")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.set_task_meta(conn, task.id, "tag", "v")  # same value
        assert fired == []

    def test_remove_meta_fires(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        service.set_task_meta(conn, task.id, "x", "1")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.remove_task_meta(conn, task.id, "x")
        assert HookEvent.TASK_META_REMOVED in fired

    def test_replace_metadata_fires_per_key(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        service.set_task_meta(conn, task.id, "a", "old")
        service.set_task_meta(conn, task.id, "b", "keep")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append((e, kw["meta_key"]))):
            service.replace_task_metadata(conn, task.id, {"a": "new", "c": "added"}, source="test")
        # key "a" changed, key "c" added (META_SET), key "b" removed (META_REMOVED)
        event_keys = [(e, k) for e, k in fired]
        assert (HookEvent.TASK_META_SET, "a") in event_keys
        assert (HookEvent.TASK_META_SET, "c") in event_keys
        assert (HookEvent.TASK_META_REMOVED, "b") in event_keys


# ---------------------------------------------------------------------------
# CLI exit code 7
# ---------------------------------------------------------------------------

class TestCliExitCode:
    def test_exit_7_on_pre_hook_rejection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from stx.cli import main, EXIT_HOOK_REJECTED
        from stx.connection import get_connection, init_db

        hooks_toml = tmp_path / "hooks.toml"
        hooks_toml.write_text(
            '[[hooks]]\nevent = "task.created"\ntiming = "pre"\ncommand = "exit 1"\n'
        )
        monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)

        db = tmp_path / "test.db"
        cli_conn = get_connection(db)
        init_db(cli_conn)
        ws = service.create_workspace(cli_conn, "cli-test")
        service.create_status(cli_conn, ws.id, "todo")
        # Persist active workspace so the CLI can resolve it
        from stx.active_workspace import set_active_workspace_id
        set_active_workspace_id(tmp_path / "tui.toml", ws.id)
        cli_conn.close()

        monkeypatch.setattr("stx.cli.DEFAULT_DB_PATH", db)

        with pytest.raises(SystemExit) as exc_info:
            main(["task", "create", "blocked-task", "--status", "todo"])
        assert exc_info.value.code == EXIT_HOOK_REJECTED


# ---------------------------------------------------------------------------
# Review-158 fix tests
# ---------------------------------------------------------------------------

class TestCreateTaskTerminalStatus:
    """H2 fix: create into terminal status fires TASK_DONE post-hook."""

    def test_terminal_status_create_fires_task_done_post(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        service.update_status(conn, st.id, {"is_terminal": True})
        fired_post = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: (
            fired_post.append(e) if t == HookTiming.POST else None
        )):
            service.create_task(conn, ws.id, "done-on-arrival", st.id)
        assert HookEvent.TASK_CREATED in fired_post
        assert HookEvent.TASK_DONE in fired_post

    def test_non_terminal_status_create_no_task_done(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        fired_post = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: (
            fired_post.append(e) if t == HookTiming.POST else None
        )):
            service.create_task(conn, ws.id, "normal", st.id)
        assert HookEvent.TASK_CREATED in fired_post
        assert HookEvent.TASK_DONE not in fired_post


class TestUpdateTaskNoOpShortCircuit:
    """H3 fix: update_task with no real delta skips hooks and DB write."""

    def test_no_change_fires_no_hooks(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.update_task(conn, task.id, {"title": task.title}, "test")
        assert fired == []

    def test_no_change_preserves_version(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        result = service.update_task(conn, task.id, {"title": task.title}, "test")
        assert result.version == task.version


class TestReplaceMetadataNormalization:
    """C1 fix: replace_task_metadata passes normalized keys into _replace_entity_metadata."""

    def test_uppercase_input_keys_normalized_in_hook_events(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired_keys = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired_keys.append(kw["meta_key"])):
            service.replace_task_metadata(conn, task.id, {"FOO": "bar"}, source="test")
        assert "foo" in fired_keys
        assert "FOO" not in fired_keys


class TestWrapperEntryPoints:
    """M3: thin wrapper functions still fire the expected hook events."""

    def test_move_task_fires_moved(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        st2 = service.create_status(conn, ws.id, "done")
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.move_task(conn, task.id, st2.id, "test")
        assert HookEvent.TASK_MOVED in fired

    def test_mark_task_done_fires_done(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.mark_task_done(conn, task.id, source="test")
        assert HookEvent.TASK_DONE in fired

    def test_mark_task_undone_fires_undone(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        service.mark_task_done(conn, task.id, source="test")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.mark_task_undone(conn, task.id, source="test")
        assert HookEvent.TASK_UNDONE in fired

    def test_assign_task_to_group_fires_assigned(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        grp = service.create_group(conn, ws.id, "grp")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.assign_task_to_group(conn, task.id, grp.id, source="test")
        assert HookEvent.TASK_ASSIGNED in fired

    def test_unassign_task_from_group_fires_unassigned(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        grp = service.create_group(conn, ws.id, "grp")
        service.assign_task_to_group(conn, task.id, grp.id, source="test")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.unassign_task_from_group(conn, task.id, source="test")
        assert HookEvent.TASK_UNASSIGNED in fired


class TestIdempotencySkips:
    """M4: idempotent paths must not fire hooks."""

    def test_mark_done_already_done_fires_no_hooks(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        service.mark_task_done(conn, task.id, source="test")
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.mark_task_done(conn, task.id, source="test")
        assert fired == []

    def test_mark_undone_not_done_fires_no_hooks(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            service.mark_task_undone(conn, task.id, source="test")
        assert fired == []

    def test_remove_meta_absent_key_fires_no_hooks(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        task = _task(conn, ws.id, st.id)
        fired = []
        with patch("stx.service.fire_hooks", side_effect=lambda e, t, **kw: fired.append(e)):
            with pytest.raises(LookupError):
                service.remove_task_meta(conn, task.id, "nonexistent")
        assert fired == []


# ---------------------------------------------------------------------------
# Task 160: group, workspace, status, and edge hook wiring
# ---------------------------------------------------------------------------

def _capture(calls: list) -> object:
    def fake(event, timing, **kw):
        calls.append((event, timing, kw))
    return fake


class TestWorkspaceHooks:
    def test_create_fires_pre_and_post(self, conn: sqlite3.Connection) -> None:
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            ws = service.create_workspace(conn, "ws1")
        pre = [c for c in calls if c[0] == HookEvent.WORKSPACE_CREATED and c[1] == HookTiming.PRE]
        post = [c for c in calls if c[0] == HookEvent.WORKSPACE_CREATED and c[1] == HookTiming.POST]
        assert len(pre) == 1 and pre[0][2]["proposed"]["name"] == "ws1"
        assert len(post) == 1 and post[0][2]["entity"] == ws

    def test_update_fires_updated_with_changes(self, conn: sqlite3.Connection) -> None:
        ws = service.create_workspace(conn, "ws1")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.update_workspace(conn, ws.id, {"name": "ws2"}, "test")
        post = [c for c in calls if c[0] == HookEvent.WORKSPACE_UPDATED and c[1] == HookTiming.POST]
        assert len(post) == 1
        assert post[0][2]["changes"]["name"] == {"old": "ws1", "new": "ws2"}

    def test_update_no_op_fires_nothing(self, conn: sqlite3.Connection) -> None:
        ws = service.create_workspace(conn, "ws1")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.update_workspace(conn, ws.id, {"name": "ws1"}, "test")
        assert calls == []

    def test_archive_fires_pre_and_post(self, conn: sqlite3.Connection) -> None:
        ws = service.create_workspace(conn, "ws1")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.cascade_archive_workspace(conn, ws.id, source="test")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.WORKSPACE_ARCHIVED) == 2

    def test_pre_rejection_blocks_create(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hooks_toml = tmp_path / "hooks.toml"
        hooks_toml.write_text(
            '[[hooks]]\nevent = "workspace.created"\ntiming = "pre"\ncommand = "exit 1"\n'
        )
        monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)
        with pytest.raises(HookRejectionError):
            service.create_workspace(conn, "blocked")
        assert service.list_workspaces(conn) == ()


class TestStatusHooks:
    def test_create_fires(self, conn: sqlite3.Connection) -> None:
        ws = service.create_workspace(conn, "ws")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            st = service.create_status(conn, ws.id, "todo")
        pre = [c for c in calls if c[0] == HookEvent.STATUS_CREATED and c[1] == HookTiming.PRE]
        post = [c for c in calls if c[0] == HookEvent.STATUS_CREATED and c[1] == HookTiming.POST]
        assert len(pre) == 1 and pre[0][2]["proposed"]["name"] == "todo"
        assert len(post) == 1 and post[0][2]["entity"].id == st.id

    def test_update_fires_with_changes(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.update_status(conn, st.id, {"name": "backlog"}, "test")
        post = [c for c in calls if c[0] == HookEvent.STATUS_UPDATED and c[1] == HookTiming.POST]
        assert len(post) == 1
        assert post[0][2]["changes"]["name"]["new"] == "backlog"

    def test_archive_fires(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.archive_status(conn, st.id, source="test")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.STATUS_ARCHIVED) == 2

    def test_pre_rejection_blocks_create(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hooks_toml = tmp_path / "hooks.toml"
        hooks_toml.write_text(
            '[[hooks]]\nevent = "status.created"\ntiming = "pre"\ncommand = "exit 1"\n'
        )
        monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)
        ws = service.create_workspace(conn, "ws")
        with pytest.raises(HookRejectionError):
            service.create_status(conn, ws.id, "todo")
        assert service.list_statuses(conn, ws.id) == ()


class TestGroupHooks:
    def test_create_fires(self, conn: sqlite3.Connection) -> None:
        ws, _ = _ws_status(conn)
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            g = service.create_group(conn, ws.id, "grp", description="d")
        pre = [c for c in calls if c[0] == HookEvent.GROUP_CREATED and c[1] == HookTiming.PRE]
        post = [c for c in calls if c[0] == HookEvent.GROUP_CREATED and c[1] == HookTiming.POST]
        assert len(pre) == 1 and pre[0][2]["proposed"]["title"] == "grp"
        assert len(post) == 1 and post[0][2]["entity"].id == g.id

    def test_update_fires_with_changes(self, conn: sqlite3.Connection) -> None:
        ws, _ = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.update_group(conn, g.id, {"title": "grp2"}, "test")
        post = [c for c in calls if c[0] == HookEvent.GROUP_UPDATED and c[1] == HookTiming.POST]
        assert len(post) == 1
        assert post[0][2]["changes"]["title"]["new"] == "grp2"

    def test_cascade_archive_fires_pre_post(self, conn: sqlite3.Connection) -> None:
        ws, _ = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.cascade_archive_group(conn, g.id, source="test")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.GROUP_ARCHIVED) == 2

    def test_cascade_archive_skips_per_task_hooks(self, conn: sqlite3.Connection) -> None:
        """Carve-out: bulk-archived tasks in a cascade do NOT fire TASK_ARCHIVED."""
        ws, st = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        service.create_task(conn, ws.id, "t1", st.id, group_id=g.id)
        service.create_task(conn, ws.id, "t2", st.id, group_id=g.id)
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.cascade_archive_group(conn, g.id, source="test")
        assert not any(e == HookEvent.TASK_ARCHIVED for e, _, _ in calls)

    def test_meta_set_fires(self, conn: sqlite3.Connection) -> None:
        ws, _ = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.set_group_meta(conn, g.id, "tag", "v")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.GROUP_META_SET) == 2  # pre + post

    def test_meta_remove_fires(self, conn: sqlite3.Connection) -> None:
        ws, _ = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        service.set_group_meta(conn, g.id, "tag", "v")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.remove_group_meta(conn, g.id, "tag")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.GROUP_META_REMOVED) == 2

    def test_replace_metadata_fires_per_key(self, conn: sqlite3.Connection) -> None:
        ws, _ = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        service.set_group_meta(conn, g.id, "a", "old")
        service.set_group_meta(conn, g.id, "b", "keep")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.replace_group_metadata(conn, g.id, {"a": "new", "c": "added"}, source="test")
        events_by_key = {(e, kw.get("meta_key")) for e, t, kw in calls if t == HookTiming.POST}
        assert (HookEvent.GROUP_META_SET, "a") in events_by_key
        assert (HookEvent.GROUP_META_SET, "c") in events_by_key
        assert (HookEvent.GROUP_META_REMOVED, "b") in events_by_key


class TestWorkspaceMetaHooks:
    def test_set_meta_fires(self, conn: sqlite3.Connection) -> None:
        ws = service.create_workspace(conn, "ws")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.set_workspace_meta(conn, ws.id, "tag", "v")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.WORKSPACE_META_SET) == 2

    def test_remove_meta_fires(self, conn: sqlite3.Connection) -> None:
        ws = service.create_workspace(conn, "ws")
        service.set_workspace_meta(conn, ws.id, "tag", "v")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.remove_workspace_meta(conn, ws.id, "tag")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.WORKSPACE_META_REMOVED) == 2


class TestEdgeHooks:
    def test_create_fires(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        pre = [c for c in calls if c[0] == HookEvent.EDGE_CREATED and c[1] == HookTiming.PRE]
        post = [c for c in calls if c[0] == HookEvent.EDGE_CREATED and c[1] == HookTiming.POST]
        assert len(pre) == 1 and pre[0][2]["proposed"]["kind"] == "blocks"
        assert len(post) == 1
        assert post[0][2]["entity"]["from_id"] == t1.id
        assert post[0][2]["entity"]["to_id"] == t2.id
        assert post[0][2]["entity"]["archived"] is False

    def test_archive_fires(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.archive_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.EDGE_ARCHIVED) == 2

    def test_update_fires_on_acyclic_flip(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="informs", acyclic=False)
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.update_edge(
                conn, ("task", t1.id), ("task", t2.id),
                kind="informs", changes={"acyclic": True}, source="test",
            )
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.EDGE_UPDATED) == 2

    def test_update_noop_skips_hooks(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks", acyclic=True)
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.update_edge(
                conn, ("task", t1.id), ("task", t2.id),
                kind="blocks", changes={"acyclic": True}, source="test",
            )
        assert calls == []

    def test_meta_set_fires(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.set_edge_meta(conn, "task", t1.id, "task", t2.id, "blocks", "tag", "v")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.EDGE_META_SET) == 2

    def test_meta_remove_fires(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        service.set_edge_meta(conn, "task", t1.id, "task", t2.id, "blocks", "tag", "v")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.remove_edge_meta(conn, "task", t1.id, "task", t2.id, "blocks", "tag")
        events = [e for e, _, _ in calls]
        assert events.count(HookEvent.EDGE_META_REMOVED) == 2

    def test_replace_metadata_fires_per_key(self, conn: sqlite3.Connection) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        service.set_edge_meta(conn, "task", t1.id, "task", t2.id, "blocks", "a", "old")
        service.set_edge_meta(conn, "task", t1.id, "task", t2.id, "blocks", "b", "keep")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.replace_edge_metadata(
                conn, "task", t1.id, "task", t2.id, "blocks",
                {"a": "new", "c": "added"}, source="test",
            )
        events_by_key = {(e, kw.get("meta_key")) for e, t, kw in calls if t == HookTiming.POST}
        assert (HookEvent.EDGE_META_SET, "a") in events_by_key
        assert (HookEvent.EDGE_META_SET, "c") in events_by_key
        assert (HookEvent.EDGE_META_REMOVED, "b") in events_by_key

    def test_pre_rejection_blocks_create(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hooks_toml = tmp_path / "hooks.toml"
        hooks_toml.write_text(
            '[[hooks]]\nevent = "edge.created"\ntiming = "pre"\ncommand = "exit 1"\n'
        )
        monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        with pytest.raises(HookRejectionError):
            service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        assert service.list_edges(conn, ws.id) == ()


# ---------------------------------------------------------------------------
# Task 160 review fixes — carve-out for workspace, idempotent archive, and
# pre-hook rejection on update/archive paths.
# ---------------------------------------------------------------------------


def _write_rejecting_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event: str
) -> None:
    hooks_toml = tmp_path / "hooks.toml"
    hooks_toml.write_text(
        f'[[hooks]]\nevent = "{event}"\ntiming = "pre"\ncommand = "exit 1"\n'
    )
    monkeypatch.setattr("stx.hooks.DEFAULT_HOOKS_PATH", hooks_toml)


class TestCascadeArchiveWorkspaceCarveOut:
    def test_skips_per_entity_hooks(self, conn: sqlite3.Connection) -> None:
        ws = service.create_workspace(conn, "ws")
        st = service.create_status(conn, ws.id, "todo")
        g = service.create_group(conn, ws.id, "grp")
        service.create_task(conn, ws.id, "t1", st.id, group_id=g.id)
        service.create_task(conn, ws.id, "t2", st.id)
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.cascade_archive_workspace(conn, ws.id, source="test")
        events = [e for e, _, _ in calls]
        # Only WORKSPACE_ARCHIVED (pre + post); no per-entity cascade hooks.
        assert HookEvent.TASK_ARCHIVED not in events
        assert HookEvent.GROUP_ARCHIVED not in events
        assert HookEvent.STATUS_ARCHIVED not in events
        assert events.count(HookEvent.WORKSPACE_ARCHIVED) == 2


class TestIdempotentArchivePayload:
    def test_workspace_second_archive_reports_old_true(
        self, conn: sqlite3.Connection
    ) -> None:
        ws = service.create_workspace(conn, "ws")
        service.cascade_archive_workspace(conn, ws.id, source="test")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.cascade_archive_workspace(conn, ws.id, source="test")
        pre_calls = [c for c in calls if c[0] == HookEvent.WORKSPACE_ARCHIVED and c[1] == HookTiming.PRE]
        assert pre_calls, "expected PRE hook on repeat archive"
        assert pre_calls[0][2]["changes"]["archived"]["old"] is True

    def test_group_second_archive_reports_old_true(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, _ = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        service.cascade_archive_group(conn, g.id, source="test")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.cascade_archive_group(conn, g.id, source="test")
        pre_calls = [c for c in calls if c[0] == HookEvent.GROUP_ARCHIVED and c[1] == HookTiming.PRE]
        assert pre_calls
        assert pre_calls[0][2]["changes"]["archived"]["old"] is True

    def test_status_second_archive_reports_old_true(
        self, conn: sqlite3.Connection
    ) -> None:
        ws, st = _ws_status(conn)
        service.archive_status(conn, st.id, source="test")
        calls: list = []
        with patch("stx.service.fire_hooks", side_effect=_capture(calls)):
            service.archive_status(conn, st.id, source="test")
        pre_calls = [c for c in calls if c[0] == HookEvent.STATUS_ARCHIVED and c[1] == HookTiming.PRE]
        assert pre_calls
        assert pre_calls[0][2]["changes"]["archived"]["old"] is True


class TestPreRejectionOnUpdateAndArchive:
    def test_update_workspace_rejection(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = service.create_workspace(conn, "ws")
        _write_rejecting_hook(tmp_path, monkeypatch, "workspace.updated")
        with pytest.raises(HookRejectionError):
            service.update_workspace(conn, ws.id, {"name": "ws2"}, "test")
        assert service.get_workspace(conn, ws.id).name == "ws"

    def test_cascade_archive_workspace_rejection(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = service.create_workspace(conn, "ws")
        _write_rejecting_hook(tmp_path, monkeypatch, "workspace.archived")
        with pytest.raises(HookRejectionError):
            service.cascade_archive_workspace(conn, ws.id, source="test")
        assert service.get_workspace(conn, ws.id).archived is False

    def test_cascade_archive_group_rejection(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, _ = _ws_status(conn)
        g = service.create_group(conn, ws.id, "grp")
        _write_rejecting_hook(tmp_path, monkeypatch, "group.archived")
        with pytest.raises(HookRejectionError):
            service.cascade_archive_group(conn, g.id, source="test")
        assert service.get_group(conn, g.id).archived is False

    def test_archive_status_rejection(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, st = _ws_status(conn)
        _write_rejecting_hook(tmp_path, monkeypatch, "status.archived")
        with pytest.raises(HookRejectionError):
            service.archive_status(conn, st.id, source="test")
        assert service.get_status(conn, st.id).archived is False

    def test_update_edge_rejection(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="informs", acyclic=False)
        _write_rejecting_hook(tmp_path, monkeypatch, "edge.updated")
        with pytest.raises(HookRejectionError):
            service.update_edge(
                conn, ("task", t1.id), ("task", t2.id),
                kind="informs", changes={"acyclic": True}, source="test",
            )
        detail = service.get_edge_detail(conn, ("task", t1.id), ("task", t2.id), kind="informs")
        assert detail.acyclic is False

    def test_archive_edge_rejection(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, st = _ws_status(conn)
        t1 = _task(conn, ws.id, st.id, "t1")
        t2 = _task(conn, ws.id, st.id, "t2")
        service.add_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        _write_rejecting_hook(tmp_path, monkeypatch, "edge.archived")
        with pytest.raises(HookRejectionError):
            service.archive_edge(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        detail = service.get_edge_detail(conn, ("task", t1.id), ("task", t2.id), kind="blocks")
        assert detail.archived is False
