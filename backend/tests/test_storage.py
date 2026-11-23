import sqlite3

import pandas as pd

from sales.clean import CleaningReport
from sales.storage import Store, file_sha256


def test_load_returns_none_when_file_missing(tmp_path):
    assert Store(tmp_path / "missing.db").load() is None


def test_load_returns_none_when_tables_missing(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    assert Store(path).load() is None


def test_load_returns_none_for_old_copy_without_checksum(tmp_path, small_sales):
    store = Store(tmp_path / "s.db")
    store.save(small_sales, CleaningReport(), "sales.csv", "abc")
    with sqlite3.connect(store.path) as conn:
        conn.execute("DELETE FROM meta WHERE key = 'csv_sha256'")
    assert store.load() is None


def test_round_trip_keeps_values_types_and_checksum(tmp_path, small_sales):
    store = Store(tmp_path / "nested" / "s.db")  # parent folder is created
    report = CleaningReport(rows_in=12, rows_out=11, duplicate_rows_removed=1, unknown_regions=["Papua"])
    store.save(small_sales, report, "sales.csv", "abc123")

    saved = store.load()
    assert (saved.source, saved.csv_sha256) == ("sales.csv", "abc123")
    assert saved.seeded_at
    assert saved.report == report
    pd.testing.assert_frame_equal(saved.df, small_sales, check_dtype=False)
    assert pd.api.types.is_datetime64_any_dtype(saved.df["date"])
    assert saved.df["is_return"].dtype == bool


def test_file_sha256(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x")
    assert file_sha256(f) == "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
