"""Load sales.csv and fix the data problems found in the sample export.

Every fix is counted in a CleaningReport so the app can show what changed.
Nothing is dropped silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = [
    "date",
    "invoice_no",
    "region",
    "branch",
    "outlet_id",
    "outlet_name",
    "outlet_type",
    "salesman",
    "brand",
    "sku",
    "qty_carton",
    "price_per_carton_idr",
    "gross_sales_idr",
    "discount_idr",
    "net_sales_idr",
]

MONEY_COLUMNS = ["price_per_carton_idr", "gross_sales_idr", "discount_idr", "net_sales_idr"]

# Canonical region names. Keys are lower-cased spellings seen in exports.
REGION_ALIASES = {
    "jabodetabek": "Jabodetabek",
    "jawa barat": "Jawa Barat",
    "jabar": "Jawa Barat",
    "jawa tengah": "Jawa Tengah",
    "jateng": "Jawa Tengah",
    "jawa timur": "Jawa Timur",
    "jatim": "Jawa Timur",
    "sumatera": "Sumatera",
    "sumatra": "Sumatera",
    "kalimantan": "Kalimantan",
}

UNKNOWN_SALESMAN = "(tidak tercatat)"


@dataclass
class CleaningReport:
    rows_in: int = 0
    rows_out: int = 0
    duplicate_rows_removed: int = 0
    region_values_fixed: int = 0
    whitespace_values_fixed: int = 0
    missing_salesman_filled: int = 0
    return_rows: int = 0
    arithmetic_mismatches: int = 0
    unknown_regions: list[str] = field(default_factory=list)

    def as_lines(self) -> list[str]:
        lines = [
            f"{self.rows_in} baris dibaca, {self.rows_out} baris dipakai.",
            f"{self.duplicate_rows_removed} baris duplikat persis dihapus.",
            f"{self.region_values_fixed} nama region diseragamkan (mis. 'Jabar', 'JAWA BARAT' jadi 'Jawa Barat').",
            f"{self.whitespace_values_fixed} nilai teks dirapikan dari spasi berlebih.",
            f"{self.missing_salesman_filled} baris tanpa nama salesman diberi label '{UNKNOWN_SALESMAN}'.",
            f"{self.return_rows} baris retur (qty negatif) tetap dihitung sebagai pengurang penjualan.",
            f"{self.arithmetic_mismatches} baris dengan qty x harga atau gross - diskon yang tidak cocok.",
        ]
        if self.unknown_regions:
            lines.append("Region tidak dikenal (dibiarkan apa adanya): " + ", ".join(self.unknown_regions))
        return lines


def load_sales(path: str | Path) -> tuple[pd.DataFrame, CleaningReport]:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    return clean_sales(raw)


def clean_sales(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    missing = [c for c in EXPECTED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Kolom wajib tidak ada di CSV: {', '.join(missing)}")

    report = CleaningReport(rows_in=len(raw))
    df = raw[EXPECTED_COLUMNS].copy()

    # Trailing or doubled spaces, e.g. "Grosir Berkah " vs "Grosir Berkah".
    for col in df.columns:
        stripped = df[col].str.strip().str.replace(r"\s+", " ", regex=True)
        report.whitespace_values_fixed += int((stripped != df[col]).sum())
        df[col] = stripped

    # Exact duplicate lines are double exports of the same invoice line.
    before = len(df)
    df = df.drop_duplicates(keep="first").reset_index(drop=True)
    report.duplicate_rows_removed = before - len(df)

    region_key = df["region"].str.lower()
    canonical = region_key.map(REGION_ALIASES)
    report.unknown_regions = sorted(df.loc[canonical.isna(), "region"].unique().tolist())
    canonical = canonical.fillna(df["region"])
    report.region_values_fixed = int((canonical != df["region"]).sum())
    df["region"] = canonical

    no_salesman = df["salesman"] == ""
    report.missing_salesman_filled = int(no_salesman.sum())
    df.loc[no_salesman, "salesman"] = UNKNOWN_SALESMAN

    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["qty_carton"] = pd.to_numeric(df["qty_carton"]).astype(int)
    for col in MONEY_COLUMNS:
        df[col] = pd.to_numeric(df[col]).astype("int64")

    report.return_rows = int((df["qty_carton"] < 0).sum())
    df["is_return"] = df["qty_carton"] < 0

    gross_ok = df["qty_carton"] * df["price_per_carton_idr"] == df["gross_sales_idr"]
    net_ok = df["gross_sales_idr"] - df["discount_idr"] == df["net_sales_idr"]
    df["arithmetic_ok"] = gross_ok & net_ok
    report.arithmetic_mismatches = int((~df["arithmetic_ok"]).sum())

    df["month"] = df["date"].dt.to_period("M").astype(str)
    report.rows_out = len(df)
    return df, report
