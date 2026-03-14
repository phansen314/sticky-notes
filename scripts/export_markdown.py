#!/usr/bin/env python3
"""Export a sticky-notes SQLite database to a Markdown report.

Usage:
    python scripts/export_markdown.py [DB_PATH] [-o OUTPUT]

    Prefer: todo export [-o OUTPUT]

Defaults:
    DB_PATH  ~/.local/share/sticky-notes/sticky-notes.db
    OUTPUT   stdout (use -o to write to a file)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sticky_notes.connection import DEFAULT_DB_PATH, get_connection
from sticky_notes.export import export_markdown


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a sticky-notes database to Markdown."
    )
    parser.add_argument(
        "db",
        nargs="?",
        default=str(DEFAULT_DB_PATH),
        help=f"path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="write to file instead of stdout",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = get_connection(db_path)
    try:
        md = export_markdown(conn)
    finally:
        conn.close()

    if args.output:
        Path(args.output).write_text(md)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
