from __future__ import annotations

import sqlite3
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer

from sticky_notes.connection import DEFAULT_DB_PATH, get_connection, init_db
from sticky_notes.tui.config import TuiConfig, load_config


class StickyNotesApp(App):
    CSS_PATH = "sticky_notes.tcss"
    TITLE = "Sticky Notes"

    conn: sqlite3.Connection
    config: TuiConfig

    def __init__(self, db_path: Path | None = None):
        super().__init__()
        self.db_path = db_path or DEFAULT_DB_PATH
        self.conn = get_connection(self.db_path)
        init_db(self.conn)
        self.config = load_config()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_unmount(self) -> None:
        if hasattr(self, "conn"):
            self.conn.close()
