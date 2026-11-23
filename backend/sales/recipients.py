"""Telegram recipients: sales managers (one region each) and their heads (overall).

Stored in the same SQLite file as the sales data, in its own tables, so
uploading a new CSV never touches the recipient list.

A recipient is ready to receive reports once it has a chat ID. Three ways:
  - config/recipients.csv, imported at startup (placeholders in the README);
  - typed in the dashboard;
  - an invite link (t.me/<bot>?start=<invite_code>); the bot calls register().
"""

from __future__ import annotations

import csv
import secrets
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROLES = {"manager": "Sales Manager", "head": "Atasan (overall)"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('manager', 'head')),
    region TEXT,
    chat_id INTEGER,
    invite_code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,
    sent_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error TEXT
);
"""


class RecipientError(ValueError):
    """Invalid recipient data; the message is safe to show to the user."""


@dataclass
class Recipient:
    id: int
    name: str
    role: str
    region: str | None
    chat_id: int | None
    invite_code: str
    created_at: str
    last_sent_at: str | None = None
    last_send_ok: bool | None = None
    last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self.chat_id is not None

    def as_dict(self) -> dict:
        return {**asdict(self), "connected": self.connected, "role_label": ROLES[self.role]}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RecipientStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def import_csv(self, path: str | Path, known_regions: list[str]) -> ImportResult:
        """Load recipients from a CSV (name,role,region,chat_id).

        Matched by name + role. A new row is added; for an existing one the
        region is updated, and the chat ID too when the file has one (an empty
        cell keeps a chat linked through an invite). Rows the dashboard added
        are left alone. Bad rows are skipped and reported, never fatal.
        """
        result = ImportResult()
        path = Path(path)
        if not path.exists():
            return result
        with path.open(newline="", encoding="utf-8-sig") as f:
            for line_no, raw in enumerate(csv.DictReader(f), start=2):
                row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
                if not any(row.values()) or row.get("name", "").startswith("#"):
                    continue
                try:
                    chat_id = _parse_chat_id(row.get("chat_id", ""))
                    role = row.get("role", "manager").lower() or "manager"
                    existing = self._find(row.get("name", ""), role)
                    if existing:
                        self.update(existing.id, known_regions, region=row.get("region") or None,
                                    **({"chat_id": chat_id} if chat_id is not None else {}))
                        result.updated += 1
                    else:
                        self.add(row.get("name", ""), role, row.get("region") or None, known_regions, chat_id)
                        result.added += 1
                except RecipientError as err:
                    result.skipped.append(f"baris {line_no}: {err}")
        return result

    def _find(self, name: str, role: str) -> Recipient | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM recipients WHERE name = ? AND role = ?", (name.strip(), role)).fetchone()
            return self.get(row["id"], conn) if row else None

    def add(self, name: str, role: str, region: str | None, known_regions: list[str],
            chat_id: int | None = None) -> Recipient:
        name, region = _validate(name, role, region, known_regions)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO recipients (name, role, region, chat_id, invite_code, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, role, region, chat_id, secrets.token_urlsafe(9), _now()),
            )
            return self.get(cur.lastrowid, conn)

    def get(self, recipient_id: int, conn: sqlite3.Connection | None = None) -> Recipient:
        own = conn is None
        conn = conn or self._connect()
        try:
            row = conn.execute(
                """
                SELECT r.*, l.sent_at AS last_sent_at, l.ok AS last_send_ok, l.error AS last_error
                FROM recipients r
                LEFT JOIN send_log l ON l.id = (SELECT MAX(id) FROM send_log WHERE recipient_id = r.id)
                WHERE r.id = ?
                """,
                (recipient_id,),
            ).fetchone()
        finally:
            if own:
                conn.close()
        if row is None:
            raise KeyError(recipient_id)
        return _to_recipient(row)

    def list(self) -> list[Recipient]:
        with self._connect() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM recipients ORDER BY role DESC, region, name"  # managers first, then heads
            )]
            return [self.get(i, conn) for i in ids]

    _UNSET = object()

    def update(self, recipient_id: int, known_regions: list[str], *, name: str | None = None,
               region: str | None = None, chat_id: int | None | object = _UNSET) -> Recipient:
        """Change name, region and/or chat ID. chat_id=None clears it."""
        current = self.get(recipient_id)
        new_name, new_region = _validate(
            current.name if name is None else name,
            current.role,
            current.region if region is None else region,
            known_regions,
        )
        new_chat = current.chat_id if chat_id is self._UNSET else chat_id
        with self._connect() as conn:
            conn.execute(
                "UPDATE recipients SET name = ?, region = ?, chat_id = ? WHERE id = ?",
                (new_name, new_region, new_chat, recipient_id),
            )
            return self.get(recipient_id, conn)

    def delete(self, recipient_id: int) -> None:
        with self._connect() as conn:
            if conn.execute("DELETE FROM recipients WHERE id = ?", (recipient_id,)).rowcount == 0:
                raise KeyError(recipient_id)

    def register(self, invite_code: str, chat_id: int) -> Recipient:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM recipients WHERE invite_code = ?", (invite_code,)).fetchone()
            if row is None:
                raise KeyError(invite_code)
            conn.execute("UPDATE recipients SET chat_id = ? WHERE id = ?", (chat_id, row["id"]))
            return self.get(row["id"], conn)

    def log_send(self, recipient_id: int, ok: bool, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO send_log (recipient_id, sent_at, ok, error) VALUES (?, ?, ?, ?)",
                (recipient_id, _now(), int(ok), error),
            )


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0
    skipped: list[str] = field(default_factory=list)


def _validate(name: str, role: str, region: str | None, known_regions: list[str]) -> tuple[str, str | None]:
    name = (name or "").strip()
    if not name:
        raise RecipientError("Nama wajib diisi.")
    if role not in ROLES:
        raise RecipientError("Peran harus 'manager' atau 'head'.")
    if role == "head":
        return name, None
    if region not in known_regions:
        raise RecipientError(f"Region tidak dikenal: {region}. Pilih salah satu: {', '.join(known_regions)}.")
    return name, region


def _parse_chat_id(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise RecipientError(f"chat_id harus angka (contoh 123456789, atau -100123 untuk grup), bukan '{value}'.") from None


def _to_recipient(row: sqlite3.Row) -> Recipient:
    data = dict(row)
    if data["last_send_ok"] is not None:
        data["last_send_ok"] = bool(data["last_send_ok"])
    return Recipient(**data)
