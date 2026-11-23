from pathlib import Path

import pandas as pd
import pytest

from sales.analysis import outlet_scorecard, sales_by, weakest_outlets
from sales.clean import EXPECTED_COLUMNS, UNKNOWN_SALESMAN, clean_sales, load_sales
from sales.summary import TELEGRAM_MAX_CHARS, build_summary, rupiah

CSV = Path(__file__).resolve().parents[2] / "data" / "sales.csv"


def row(**overrides):
    base = {
        "date": "2026-09-01", "invoice_no": "INV1", "region": "Jawa Barat", "branch": "Bandung",
        "outlet_id": "OUT1", "outlet_name": "Toko A", "outlet_type": "Toko Kelontong",
        "salesman": "Andi", "brand": "Sukro", "sku": "Sukro Pedas 100g", "qty_carton": "2",
        "price_per_carton_idr": "100", "gross_sales_idr": "200", "discount_idr": "0",
        "net_sales_idr": "200",
    }
    base.update(overrides)
    return base


def frame(*rows):
    return pd.DataFrame(list(rows), columns=EXPECTED_COLUMNS)


def test_region_aliases_and_case_are_merged():
    df, report = clean_sales(frame(row(), row(invoice_no="INV2", region="Jabar"),
                                   row(invoice_no="INV3", region="JAWA BARAT")))
    assert df["region"].unique().tolist() == ["Jawa Barat"]
    assert report.region_values_fixed == 2


def test_exact_duplicates_removed_but_same_sku_on_other_invoice_kept():
    df, report = clean_sales(frame(row(), row(), row(invoice_no="INV2")))
    assert len(df) == 2
    assert report.duplicate_rows_removed == 1


def test_trailing_space_in_outlet_name_is_trimmed():
    df, _ = clean_sales(frame(row(outlet_name="Toko A "), row(invoice_no="INV2")))
    assert df["outlet_name"].unique().tolist() == ["Toko A"]


def test_missing_salesman_is_labelled_not_dropped():
    df, report = clean_sales(frame(row(salesman="")))
    assert df.loc[0, "salesman"] == UNKNOWN_SALESMAN
    assert report.missing_salesman_filled == 1


def test_return_reduces_sales():
    df, report = clean_sales(frame(
        row(),
        row(invoice_no="RTR1", qty_carton="-1", gross_sales_idr="-100", net_sales_idr="-100"),
    ))
    assert report.return_rows == 1
    assert df["net_sales_idr"].sum() == 100


def test_arithmetic_mismatch_is_counted():
    _, report = clean_sales(frame(row(net_sales_idr="999")))
    assert report.arithmetic_mismatches == 1


def test_missing_column_raises():
    with pytest.raises(ValueError, match="net_sales_idr"):
        clean_sales(frame(row()).drop(columns=["net_sales_idr"]))


def test_rupiah_format():
    assert rupiah(1_725_000_000) == "Rp1,73 M"
    assert rupiah(256_821_700) == "Rp256,8 jt"
    assert rupiah(-528_000) == "-Rp528.000"


@pytest.fixture(scope="module")
def real():
    df, report = load_sales(CSV)
    card = outlet_scorecard(df)
    return df, report, card, weakest_outlets(card)


def test_real_data_cleaning_counts(real):
    _, report, _, _ = real
    assert report.rows_in == 1891
    assert report.duplicate_rows_removed == 3
    assert report.return_rows == 1
    assert report.missing_salesman_filled == 5


def test_region_totals_add_up_to_grand_total(real):
    df, _, _, _ = real
    assert sales_by(df, "region")["total"].sum() == df["net_sales_idr"].sum()
    assert sales_by(df, "brand")["total"].sum() == df["net_sales_idr"].sum()


def test_weakest_are_five_existing_outlets_and_never_new(real):
    _, _, card, weakest = real
    assert len(weakest) == 5
    assert not weakest["is_new"].any()
    assert (weakest["weakness_score"] <= card.loc[~card["is_new"], "weakness_score"].nsmallest(5).max()).all()


def test_summary_fits_telegram_and_names_weakest(real):
    df, _, _, weakest = real
    text = build_summary(df, weakest)
    assert len(text) <= TELEGRAM_MAX_CHARS
    assert "\n" not in text
    for name in weakest["outlet_name"]:
        assert name in text


def test_unknown_region_is_kept_and_reported():
    df, report = clean_sales(frame(row(region="Papua")))
    assert df.loc[0, "region"] == "Papua"
    assert report.unknown_regions == ["Papua"]
    assert any("Papua" in line for line in report.as_lines())
