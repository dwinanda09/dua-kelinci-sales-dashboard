"""Seeder for the sales data in SQLite.

The app calls seed_if_empty() at startup: it writes data/sales.csv to the
database only when the database has no sales data yet (first setup). Every
later start reads the saved copy, even if the CSV has changed since.

Manual use (inside the app container, or with ./setup.sh):
    python -m sales.seed status                 what is in the database
    python -m sales.seed seed                   seed only if empty
    python -m sales.seed reseed [--csv PATH]    replace the sales data from a CSV
    python -m sales.seed clear --yes            delete the sales data (recipients kept)
    python -m sales.seed clear --yes --all      also delete recipients and the send log
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from .analysis import months_in
from .clean import load_sales
from .storage import Saved, Store, file_sha256

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = Path(os.getenv("SALES_CSV", ROOT / "data" / "sales.csv"))
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "var" / "sales.db"))


@dataclass
class SeedResult:
    saved: Saved
    seeded: bool  # True when this call wrote the data
    csv_changed: bool  # True when the CSV on disk differs from what was seeded


def reseed(store: Store, csv_path: Path) -> Saved:
    """Clean the CSV and replace the sales data with it."""
    df, report = load_sales(csv_path)
    months_in(df)  # refuse a file with fewer than 2 months before touching the database
    store.save(df, report, csv_path.name, file_sha256(csv_path))
    return store.load()


def seed_if_empty(store: Store, csv_path: Path) -> SeedResult:
    saved = store.load()
    if saved is None:
        return SeedResult(reseed(store, csv_path), seeded=True, csv_changed=False)
    return SeedResult(saved, seeded=False, csv_changed=csv_changed(saved, csv_path))


def csv_changed(saved: Saved, csv_path: Path) -> bool:
    """True when the file the data was seeded from has been edited since.
    Data reseeded from another file on purpose is not reported."""
    if saved.source != csv_path.name or not csv_path.exists():
        return False
    return file_sha256(csv_path) != saved.csv_sha256


def clear_recipients(db_path: Path) -> None:
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS send_log")
        conn.execute("DROP TABLE IF EXISTS recipients")


def main(argv: list[str] | None = None, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m sales.seed", description="Manage the sales data in SQLite.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show what is in the database")
    sub.add_parser("seed", help="seed from the CSV only if the database is empty")
    re_p = sub.add_parser("reseed", help="replace the sales data from a CSV")
    re_p.add_argument("--csv", type=Path, default=DEFAULT_CSV, help=f"CSV to load (default {DEFAULT_CSV})")
    cl_p = sub.add_parser("clear", help="delete the sales data")
    cl_p.add_argument("--yes", action="store_true", help="confirm the deletion")
    cl_p.add_argument("--all", action="store_true", help="also delete recipients and the send log")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"SQLite file (default {DB_PATH})")
    args = parser.parse_args(argv)
    store = Store(args.db)

    def say(text: str) -> None:
        print(text, file=out)

    if args.command == "status":
        saved = store.load()
        if saved is None:
            say(f"Belum ada data penjualan di {args.db}. Akan di-seed dari {DEFAULT_CSV.name} saat app start.")
            return 0
        say(f"Data: {saved.source}, {len(saved.df)} baris, di-seed {saved.seeded_at or '-'}")
        if csv_changed(saved, DEFAULT_CSV):
            say(f"Catatan: {DEFAULT_CSV.name} sudah berubah sejak di-seed. Jalankan 'reseed' untuk memakainya.")
        return 0

    if args.command == "seed":
        result = seed_if_empty(store, DEFAULT_CSV)
        say("Di-seed dari " + DEFAULT_CSV.name if result.seeded else "Sudah ada data; tidak ada yang diubah.")
        return 0

    if args.command == "reseed":
        if not args.csv.exists():
            say(f"File tidak ditemukan: {args.csv}")
            return 1
        try:
            saved = reseed(store, args.csv)
        except ValueError as err:
            say(f"CSV tidak bisa dipakai, data lama tetap: {err}")
            return 1
        say(f"Data diganti dari {saved.source}: {len(saved.df)} baris. Restart app untuk memakainya.")
        return 0

    # clear
    if not args.yes:
        say("Tambahkan --yes untuk benar-benar menghapus.")
        return 1
    had = store.clear()
    if args.all:
        clear_recipients(args.db)
    say(("Data penjualan dihapus" if had else "Tidak ada data penjualan")
        + ("; penerima dan log kirim juga dihapus" if args.all else "")
        + ". App akan seed ulang dari CSV saat start berikutnya.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
