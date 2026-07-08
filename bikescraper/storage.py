"""Tracks which listings we've already emailed about, so re-runs only
notify on genuinely new matches.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "seen.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_listings (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            first_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    return conn


def filter_unseen(listings):
    """Return only the listings whose id hasn't been recorded before."""
    conn = _connect()
    try:
        seen_ids = {row[0] for row in conn.execute("SELECT id FROM seen_listings")}
        return [item for item in listings if item["id"] not in seen_ids]
    finally:
        conn.close()


def mark_seen(listings):
    conn = _connect()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_listings (id, source) VALUES (?, ?)",
            [(item["id"], item["source"]) for item in listings],
        )
        conn.commit()
    finally:
        conn.close()
