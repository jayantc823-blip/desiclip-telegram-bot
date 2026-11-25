"""Small SQLite persistence layer for stream watchlist and clip counters."""
import sqlite3
from pathlib import Path
from typing import Optional

class Database:
    def __init__(self, path: Path):
        self.path = path
        self._init()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _init(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS streamers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_live INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);
                INSERT OR IGNORE INTO stats(key,value) VALUES ('clips',0);
            """)

    def add_streamer(self, url: str, title: str = "") -> int:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO streamers(url,title) VALUES(?,?)", (url, title or url))
            row = db.execute("SELECT id FROM streamers WHERE url=?", (url,)).fetchone()
            return int(row[0])

    def streamers(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM streamers ORDER BY id")]

    def remove_streamer(self, streamer_id: int) -> bool:
        with self._connect() as db:
            cur = db.execute("DELETE FROM streamers WHERE id=?", (streamer_id,))
            return cur.rowcount > 0

    def set_live(self, streamer_id: int, live: bool) -> bool:
        """Return true only on the transition into a live state."""
        with self._connect() as db:
            row = db.execute("SELECT last_live FROM streamers WHERE id=?", (streamer_id,)).fetchone()
            if row is None:
                return False
            was_live = bool(row[0])
            db.execute("UPDATE streamers SET last_live=? WHERE id=?", (int(live), streamer_id))
            return live and not was_live

    def increment_clips(self, count: int = 1):
        with self._connect() as db:
            db.execute("UPDATE stats SET value=value+? WHERE key='clips'", (count,))

    def clip_count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT value FROM stats WHERE key='clips'").fetchone()[0])
