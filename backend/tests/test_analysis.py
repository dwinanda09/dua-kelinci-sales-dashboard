"""Unit tests for sales/analysis.py on the hand-checkable `small_sales` fixture."""

import pytest

from conftest import make_sales, sales_line
from sales.analysis import months_in, outlet_scorecard, region_brand_matrix, sales_by, weakest_outlets


def test_months_in_picks_last_two_months(small_sales):
    m = months_in(small_sales)
    assert (m.previous, m.latest) == ("2026-09", "2026-10")


def test_months_in_needs_two_months():
    one_month = make_sales([sales_line("2026-09-01", "A", "Warung", "Sumatera", "Sukro", 100)])
    with pytest.raises(ValueError, match="minimal 2 bulan"):
        months_in(one_month)


def test_sales_by_region_totals_change_and_share(small_sales):
    table = sales_by(small_sales, "region")
    # Sorted by 2-month total: Jabodetabek 3600, Jawa Barat 350, Sumatera 330
    assert table.index.tolist() == ["Jabodetabek", "Jawa Barat", "Sumatera"]
    assert table.loc["Jabodetabek", "total"] == 3600
    assert table.loc["Jawa Barat", "change_pct"] == pytest.approx(-25.0)
    assert table.loc["Sumatera", "change_pct"] == pytest.approx(130.0)
    assert table["share_pct"].sum() == pytest.approx(100.0)


def test_sales_by_change_is_empty_when_previous_month_is_zero():
    df = make_sales([
        sales_line("2026-09-01", "A", "Warung", "Sumatera", "Sukro", 100),
        sales_line("2026-10-01", "A", "Warung", "Sumatera", "Deka", 100),
    ])
    table = sales_by(df, "brand")
    assert table["change_pct"].isna().loc["Deka"]  # no September sales: no % change, not infinity


def test_region_brand_matrix(small_sales):
    matrix = region_brand_matrix(small_sales)
    assert matrix.loc["Sumatera", "Tos Tos"] == 250
    assert matrix.loc["Sumatera", "Sukro"] == 80
    assert matrix.loc["Jawa Barat", "Tos Tos"] == 0


def test_scorecard_measures(small_sales):
    card = outlet_scorecard(small_sales)
    assert card.loc["B", "change_pct"] == pytest.approx(-50.0)
    # Toko Kelontong October median = median(100, 50, 150, 80) = 90
    assert card.loc["B", "peer_index"] == pytest.approx(50 / 90)
    # Grosir October median = median(500, 1100) = 800
    assert card.loc["G1", "peer_index"] == pytest.approx(500 / 800)
    # The latest date in the data is 31 Oct; B last ordered on 1 Oct.
    assert card.loc["B", "days_since_order"] == 30
    assert card.loc["C", "days_since_order"] == 0


def test_scorecard_scores_match_hand_calculation(small_sales):
    card = outlet_scorecard(small_sales)
    # trend ranks: B,G1 -50% tie -> 0.3; A 0% -> 0.6; G2 +10% -> 0.8; C +50% -> 1.0
    # peer ranks:  B 0.2; G1 0.4; A 0.6; G2 0.8; C 1.0
    expected = {"B": 0.25, "G1": 0.35, "A": 0.6, "G2": 0.8, "C": 1.0}
    for outlet, score in expected.items():
        assert card.loc[outlet, "weakness_score"] == pytest.approx(score)


def test_new_outlet_is_marked_and_never_scored(small_sales):
    card = outlet_scorecard(small_sales)
    assert card.loc["D", "is_new"]
    assert card["weakness_score"].isna().loc["D"]
    assert "D" not in weakest_outlets(card, n=10).index


def test_weakest_order_and_reason(small_sales):
    weakest = weakest_outlets(outlet_scorecard(small_sales), n=2)
    assert weakest.index.tolist() == ["B", "G1"]
    assert weakest.loc["B", "reason"] == (
        "turun 50% dari bulan lalu; hanya 56% dari median Toko Kelontong; belum order 30 hari"
    )


def test_reason_for_growing_outlet_says_naik(small_sales):
    weakest = weakest_outlets(outlet_scorecard(small_sales), n=5)
    assert weakest.loc["C", "reason"].startswith("naik 50% dari bulan lalu")
    assert "belum order" not in weakest.loc["C", "reason"]  # ordered on the last day
