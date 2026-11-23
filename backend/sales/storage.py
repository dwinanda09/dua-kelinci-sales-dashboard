"""SQLite storage for the sales data.

The data is static: it comes only from data/sales.csv, there is no upload.
It is written once, on first setup (see sales/seed.py), and read from SQLite
on every start after that. The database file lives in a Docker volume, so it
survives `docker compose down` / `up` and container restarts.

A SHA-256 of the seeded CSV is stored with it, so a later change to the file
can be reported instead of silently ignored.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .clean import CleaningReport


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class Saved:
    df: pd.DataFrame
    report: CleaningReport
    source: str
    csv_sha256: str
    seeded_at: str


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, df: pd.DataFrame, report: CleaningReport, source: str, csv_sha256: str) -> None:
        with self._connect() as conn:
            stored = df.assign(date=df["date"].dt.strftime("%Y-%m-%d"))
            stored.to_sql("sales", conn, if_exists="replace", index=False)
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.executemany(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                [
                    ("source", source),
                    ("report", json.dumps(asdict(report))),
                    ("csv_sha256", csv_sha256),
                    ("seeded_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                ],
            )

    def load(self) -> Saved | None:
        meta = self._meta()
        if meta is None:
            return None
        with self._connect() as conn:
            df = pd.read_sql("SELECT * FROM sales", conn)
        df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
        for col in ("is_return", "arithmetic_ok"):
            df[col] = df[col].astype(bool)
        return Saved(df, CleaningReport(**json.loads(meta["report"])), meta["source"],
                     meta["csv_sha256"], meta.get("seeded_at", ""))

    def is_seeded(self) -> bool:
        return self._meta() is not None

    def clear(self) -> bool:
        """Delete the sales data (not the recipients). Returns whether anything was there."""
        if not self.path.exists():
            return False
        with self._connect() as conn:
            had = self._tables(conn) >= {"sales", "meta"}
            conn.execute("DROP TABLE IF EXISTS sales")
            conn.execute("DROP TABLE IF EXISTS meta")
        return had

    def _meta(self) -> dict | None:
        if not self.path.exists():
            return None
        with self._connect() as conn:
            if not self._tables(conn) >= {"sales", "meta"}:
                return None
            meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        return meta if "csv_sha256" in meta else None

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
