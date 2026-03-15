from __future__ import annotations

from pathlib import Path

import pytest

from sticky_notes import service
from sticky_notes.connection import DEFAULT_DB_PATH
from sticky_notes.tui.app import StickyNotesApp
from sticky_notes.tui.config import TuiConfig, load_config, save_config
from sticky_notes.tui.screens.settings import SettingsScreen
from sticky_notes.tui.widgets import BoardView, ColumnWidget, TaskCard
from textual.widgets import Static


# ---- Config unit tests ----


class TestTuiConfig:
    def test_defaults(self):
        config = TuiConfig()
        assert config.theme == "dark"
        assert config.show_task_descriptions is True
        assert config.show_archived is False
        assert config.confirm_archive is True
        assert config.default_priority == 1

    def test_load_missing_file(self, tmp_path: Path):
        config = load_config(tmp_path / "nonexistent.toml")
        assert config == TuiConfig()

    def test_save_load_roundtrip(self, tmp_path: Path):
        path = tmp_path / "tui.toml"
        original = TuiConfig(
            theme="light",
            show_task_descriptions=False,
            show_archived=True,
            confirm_archive=False,
            default_priority=3,
        )
        save_config(original, path)
        loaded = load_config(path)
        assert loaded.theme == "light"
        assert loaded.show_task_descriptions is False
        assert loaded.show_archived is True
        assert loaded.confirm_archive is False
        assert loaded.default_priority == 3

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "nested" / "dir" / "tui.toml"
        save_config(TuiConfig(), path)
        assert path.exists()

    def test_load_partial_config(self, tmp_path: Path):
        path = tmp_path / "tui.toml"
        path.write_text('theme = "light"\n')
        config = load_config(path)
        assert config.theme == "light"
        assert config.default_priority == 1  # default preserved

    def test_save_format(self, tmp_path: Path):
        path = tmp_path / "tui.toml"
        save_config(TuiConfig(), path)
        text = path.read_text()
        assert 'theme = "dark"' in text
        assert "show_task_descriptions = true" in text
        assert "show_archived = false" in text
        assert "default_priority = 1" in text


# ---- TUI app + settings screen pilot tests ----


@pytest.fixture
def tui_db_path(tmp_path: Path) -> Path:
    return tmp_path / "tui-test.db"


class TestStickyNotesApp:
    async def test_app_mounts_with_injected_db(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test() as pilot:
            assert app.db_path == tui_db_path
            assert tui_db_path.exists()
            assert hasattr(app, "conn")
            assert hasattr(app, "config")

    def test_app_default_db_path(self):
        app = StickyNotesApp()
        assert app.db_path == DEFAULT_DB_PATH

    async def test_dark_mode_from_config(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test():
            assert app.dark is True


class TestSettingsScreen:
    async def test_settings_screen_mounts(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)

    async def test_db_path_displayed(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.pause()
            db_path_widget = app.screen.query_one("#db-path", Static)
            assert str(tui_db_path) in str(db_path_widget.render())

    async def test_db_size_displayed(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.pause()
            db_size_widget = app.screen.query_one("#db-size", Static)
            renderable = str(db_size_widget.render())
            assert "Size:" in renderable
            assert "KB" in renderable or "B" in renderable

    async def test_escape_pops_settings(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, SettingsScreen)

    async def test_settings_uses_app_config(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.pause()
            assert app.screen.typed_app.config is app.config


# ---- Board view tests ----


class TestBoardView:
    async def test_seeded_board_renders_three_columns(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test():
            columns = app.query(ColumnWidget)
            assert len(columns) == 3

    async def test_seeded_board_renders_eight_task_cards(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test():
            cards = app.query(TaskCard)
            assert len(cards) == 8

    async def test_column_headers_contain_names(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test():
            headers = app.query(".column-header")
            header_texts = [str(h.render()) for h in headers]
            assert any("Todo" in t for t in header_texts)
            assert any("In Progress" in t for t in header_texts)
            assert any("Done" in t for t in header_texts)

    async def test_empty_db_shows_no_board_message(self, tui_db_path: Path):
        app = StickyNotesApp(db_path=tui_db_path)
        async with app.run_test():
            msg = app.query_one("#no-board-message", Static)
            assert "No active board" in str(msg.render())

    async def test_task_cards_contain_expected_text(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test():
            cards = app.query(TaskCard)
            texts = [str(c.render()) for c in cards]
            assert any("task-" in t for t in texts)
            assert any("[P" in t for t in texts)

    async def test_archived_task_hidden_by_default(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        # Archive one task
        from sticky_notes.connection import get_connection

        conn = get_connection(db_path)
        service.update_task(
            conn, ids["task_ids"]["scaffold"], {"archived": True}, "test"
        )
        conn.close()

        app = StickyNotesApp(db_path=db_path)
        async with app.run_test():
            cards = app.query(TaskCard)
            assert len(cards) == 7


# ---- Board navigation tests ----


class TestBoardNavigation:
    """Keyboard navigation across the 2D grid of columns and task cards."""

    @staticmethod
    async def _wait_for_board(pilot) -> None:
        """Wait for board to mount and initial focus to be set."""
        await pilot.pause()

    @staticmethod
    def _board(app: StickyNotesApp) -> BoardView:
        return app.query_one(BoardView)

    async def test_initial_focus_on_first_card(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            assert self._board(app).focused_position == (0, 0)
            assert isinstance(app.focused, TaskCard)

    async def test_down_arrow_moves_to_next_card(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            await pilot.press("down")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 1)

    async def test_up_arrow_moves_to_previous_card(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 0)

    async def test_up_at_top_stays_clamped(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            await pilot.press("up")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 0)

    async def test_down_at_bottom_stays_clamped(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            # Todo column has 4 tasks, go to the bottom
            await pilot.press("down", "down", "down")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 3)
            # One more down should stay at bottom
            await pilot.press("down")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 3)

    async def test_right_arrow_moves_to_next_column(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            await pilot.press("right")
            await pilot.pause()
            assert self._board(app).focused_position == (1, 0)

    async def test_left_arrow_moves_to_previous_column(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            await pilot.press("right")
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 0)

    async def test_left_at_first_column_stays(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            await pilot.press("left")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 0)

    async def test_right_at_last_column_stays(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            # Move to last column (Done, col 2)
            await pilot.press("right", "right")
            await pilot.pause()
            pos = self._board(app).focused_position
            assert pos is not None and pos[0] == 2
            # One more right should stay
            await pilot.press("right")
            await pilot.pause()
            assert self._board(app).focused_position == pos

    async def test_vertical_position_clamped_on_column_switch(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            # Go to task index 3 in Todo (4 tasks: 0,1,2,3)
            await pilot.press("down", "down", "down")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 3)
            # Move right to In Progress (only 2 tasks: 0,1)
            await pilot.press("right")
            await pilot.pause()
            assert self._board(app).focused_position == (1, 1)  # clamped

    async def test_focused_card_has_focus_property(
        self, seeded_tui_db: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            focused = app.focused
            assert isinstance(focused, TaskCard)
            assert focused.has_focus

    async def test_right_skips_empty_column(
        self, seeded_tui_db_empty_middle: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db_empty_middle
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            assert self._board(app).focused_position == (0, 0)
            # Right should skip empty In Progress (col 1) -> Done (col 2)
            await pilot.press("right")
            await pilot.pause()
            assert self._board(app).focused_position == (2, 0)

    async def test_left_skips_empty_column(
        self, seeded_tui_db_empty_middle: tuple[Path, dict]
    ):
        db_path, ids = seeded_tui_db_empty_middle
        app = StickyNotesApp(db_path=db_path)
        async with app.run_test() as pilot:
            await self._wait_for_board(pilot)
            # Navigate to Done (col 2) — skips empty col 1
            await pilot.press("right")
            await pilot.pause()
            assert self._board(app).focused_position == (2, 0)
            # Left should skip empty In Progress (col 1) -> Todo (col 0)
            await pilot.press("left")
            await pilot.pause()
            assert self._board(app).focused_position == (0, 0)
