"""The seeder: first-setup seeding, manual reseed and cleanup, and its CLI."""

import io
import shutil
import sqlite3

import pytest

from sales.recipients import RecipientStore
from sales.seed import main, reseed, seed_if_empty
from sales.storage import Store


@pytest.fixture
def csv_file(tmp_path):
    import api

    path = tmp_path / "sales.csv"
    shutil.copy(api.DEFAULT_CSV, path)
    return path


def run(*args):
    out = io.StringIO()
    code = main(list(args), out=out)
    return code, out.getvalue()


def test_seed_if_empty_seeds_once(tmp_path, csv_file):
    store = Store(tmp_path / "s.db")
    first = seed_if_empty(store, csv_file)
    second = seed_if_empty(store, csv_file)
    assert first.seeded and not second.seeded
    assert not second.csv_changed
    assert len(second.saved.df) == 1888


def test_seed_if_empty_with_missing_csv_after_setup_keeps_data(tmp_path, csv_file):
    store = Store(tmp_path / "s.db")
    seed_if_empty(store, csv_file)
    csv_file.unlink()
    result = seed_if_empty(store, csv_file)
    assert not result.seeded and not result.csv_changed
    assert len(result.saved.df) == 1888


def test_reseed_replaces_data_and_bad_file_keeps_old(tmp_path, csv_file):
    store = Store(tmp_path / "s.db")
    seed_if_empty(store, csv_file)
    lines = csv_file.read_text(encoding="utf-8").splitlines(keepends=True)
    smaller = tmp_path / "smaller.csv"
    smaller.write_text("".join(lines[:-100]), encoding="utf-8")
    assert len(reseed(store, smaller).df) < 1888
    # Seeded from another file on purpose: not reported as "sales.csv changed".
    assert not seed_if_empty(store, csv_file).csv_changed

    one_month = tmp_path / "sep.csv"
    one_month.write_text("".join(lines[:400]), encoding="utf-8")
    with pytest.raises(ValueError):
        reseed(store, one_month)
    assert store.load().source == "smaller.csv"  # untouched by the failed reseed


def test_cli_status_seed_reseed_clear(tmp_path, csv_file, monkeypatch):
    import sales.seed

    monkeypatch.setattr(sales.seed, "DEFAULT_CSV", csv_file)
    db = str(tmp_path / "s.db")

    code, out = run("--db", db, "status")
    assert code == 0 and "Belum ada data" in out

    code, out = run("--db", db, "seed")
    assert code == 0 and "Di-seed" in out
    code, out = run("--db", db, "seed")
    assert "Sudah ada data" in out

    code, out = run("--db", db, "status")
    assert "1888 baris" in out and "berubah" not in out

    csv_file.write_text(csv_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    code, out = run("--db", db, "status")
    assert "sudah berubah sejak di-seed" in out

    code, out = run("--db", db, "reseed", "--csv", str(csv_file))
    assert code == 0 and "Data diganti" in out

    code, out = run("--db", db, "reseed", "--csv", str(tmp_path / "nope.csv"))
    assert code == 1 and "tidak ditemukan" in out

    lines = csv_file.read_text(encoding="utf-8").splitlines(keepends=True)
    one_month = tmp_path / "sep.csv"
    one_month.write_text("".join(lines[:400]), encoding="utf-8")
    code, out = run("--db", db, "reseed", "--csv", str(one_month))
    assert code == 1 and "data lama tetap" in out


def test_cli_clear_needs_yes_and_keeps_recipients_unless_all(tmp_path, csv_file, monkeypatch):
    import sales.seed

    monkeypatch.setattr(sales.seed, "DEFAULT_CSV", csv_file)
    db = tmp_path / "s.db"
    run("--db", str(db), "seed")
    RecipientStore(db).add("Pak A", "manager", "Sumatera", ["Sumatera"], chat_id=1)

    code, out = run("--db", str(db), "clear")
    assert code == 1 and "--yes" in out
    assert Store(db).is_seeded()

    code, out = run("--db", str(db), "clear", "--yes")
    assert code == 0 and "Data penjualan dihapus" in out
    assert not Store(db).is_seeded()
    assert len(RecipientStore(db).list()) == 1  # recipients kept

    code, out = run("--db", str(db), "clear", "--yes", "--all")
    assert "Tidak ada data penjualan" in out and "penerima" in out
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "recipients" not in tables


def test_clear_on_missing_database(tmp_path):
    from sales.seed import clear_recipients

    assert Store(tmp_path / "none.db").clear() is False
    clear_recipients(tmp_path / "none.db")  # no error
