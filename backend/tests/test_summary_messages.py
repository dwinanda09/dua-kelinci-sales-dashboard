"""Unit tests for the summary paragraph and the Telegram message texts."""

import pytest

from sales.analysis import outlet_scorecard, weakest_outlets
from sales.messages import COMMANDS, build_message
from sales.summary import build_summary, month_label, rupiah, signed_pct


@pytest.mark.parametrize(
    "value, text",
    [
        (1_725_000_000, "Rp1,73 M"),
        (256_821_700, "Rp256,8 jt"),
        (1_000_000, "Rp1,0 jt"),
        (999_999, "Rp999.999"),
        (0, "Rp0"),
        (-528_000, "-Rp528.000"),
        (-31_600_000, "-Rp31,6 jt"),
    ],
)
def test_rupiah(value, text):
    assert rupiah(value) == text


def test_signed_pct_and_month_label():
    assert signed_pct(92.4) == "+92%"
    assert signed_pct(-13.9) == "-14%"
    assert signed_pct(0) == "+0%"
    assert month_label("2026-10") == "Oktober 2026"


def test_summary_states_the_right_facts(small_sales):
    weakest = weakest_outlets(outlet_scorecard(small_sales), n=2)
    text = build_summary(small_sales, weakest)
    assert text.startswith("Penjualan bersih Oktober 2026 Rp1.980, -14% dari September 2026.")
    assert "Jabodetabek tetap region terbesar" in text
    assert "Sumatera tumbuh paling cepat (+130%, terutama dari Toko D Cabang Sumatera +Rp80)" in text
    assert "Jawa Barat turun paling dalam (-25%, terbesar di Toko B Cabang Jawa Barat -Rp50)" in text
    assert "Sukro menyumbang 94% penjualan" in text
    assert "Toko B (Cabang Jawa Barat, -50%), Grosir G1 (Cabang Jabodetabek, -50%)." in text
    assert "\n" not in text


def test_region_message_is_sorted_by_latest_month(small_sales):
    text = build_message("region", small_sales)
    lines = text.splitlines()
    assert lines[0] == "Penjualan per region, Oktober 2026 (vs September 2026):"
    assert lines[1] == "1. Jabodetabek: Rp1.600 (-20%)"
    assert lines[2] == "2. Sumatera: Rp230 (+130%)"
    assert lines[3] == "3. Jawa Barat: Rp150 (-25%)"
    assert lines[-1] == "Total: Rp1.980 (-14%)"


def test_brand_message_marks_new_brand():
    from conftest import make_sales, sales_line

    df = make_sales([
        sales_line("2026-09-01", "A", "Warung", "Sumatera", "Sukro", 100),
        sales_line("2026-10-01", "A", "Warung", "Sumatera", "Sukro", 100),
        sales_line("2026-10-02", "A", "Warung", "Sumatera", "Deka", 50),
    ])
    assert "Deka: Rp50 (baru)" in build_message("brand", df)


def test_weakest_message_lists_id_salesman_and_reason(small_sales):
    text = build_message("terlemah", small_sales)
    assert "1. Toko B (B, Cabang Jawa Barat), salesman Andi" in text
    assert "Rp100 -> Rp50; turun 50% dari bulan lalu" in text


def test_every_command_builds_and_unknown_raises(small_sales):
    for name in COMMANDS:
        assert build_message(name, small_sales)
    with pytest.raises(KeyError):
        build_message("nope", small_sales)


def test_summary_over_telegram_limit_raises(small_sales, monkeypatch):
    import sales.summary

    monkeypatch.setattr(sales.summary, "TELEGRAM_MAX_CHARS", 50)
    weakest = weakest_outlets(outlet_scorecard(small_sales), n=2)
    with pytest.raises(ValueError, match="4096"):
        build_summary(small_sales, weakest)


def test_region_report_for_manager(small_sales):
    from sales.messages import region_report

    text = region_report(small_sales, "Jawa Barat")
    lines = text.splitlines()
    assert lines[0] == "Laporan region Jawa Barat, Oktober 2026"
    # October: Jabodetabek 1600, Sumatera 230, Jawa Barat 150
    assert lines[1] == "Penjualan bersih Rp150, -25% dari September 2026 (peringkat 3 dari 3 region)."
    assert "- Cabang Jawa Barat: Rp150 (-25%)" in text
    assert "Brand terbesar: Sukro Rp150 (-25%)." in text
    assert "Brand paling melemah: Sukro (-25%)." in text
    assert "1. Toko B (B, Cabang Jawa Barat)" in text  # weakest first
    assert "Grosir" not in text  # only this region's outlets


def test_region_report_lists_new_outlets_and_skips_falling_brand_when_none(small_sales):
    from sales.messages import region_report

    text = region_report(small_sales, "Sumatera")
    assert "Outlet baru: Toko D (Cabang Sumatera)." in text
    assert "paling melemah" not in text  # Tos Tos grew, Sukro is new


def test_region_report_unknown_region(small_sales):
    from sales.messages import region_report

    with pytest.raises(KeyError):
        region_report(small_sales, "Papua")


def test_report_for_head_is_summary_plus_every_region(small_sales):
    from sales.messages import report_for

    text = report_for("head", None, small_sales)
    assert text.startswith("Penjualan bersih Oktober 2026")
    for region in ("Jabodetabek", "Sumatera", "Jawa Barat"):
        assert f"{region}: Rp" in text
    assert report_for("manager", "Sumatera", small_sales).startswith("Laporan region Sumatera")
