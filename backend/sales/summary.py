"""One-paragraph summary for a sales manager, written for Telegram.

Built from a template, not an LLM, so every number matches the dashboard.
Plain text only: no Markdown, so it pastes cleanly into any chat.
"""

from __future__ import annotations

import pandas as pd

from .analysis import months_in, sales_by

MONTH_NAMES = {
    "01": "Januari", "02": "Februari", "03": "Maret", "04": "April",
    "05": "Mei", "06": "Juni", "07": "Juli", "08": "Agustus",
    "09": "September", "10": "Oktober", "11": "November", "12": "Desember",
}

TELEGRAM_MAX_CHARS = 4096


def rupiah(value: float) -> str:
    """Short IDR format used by sales teams: Rp1,73 M / Rp257,0 jt."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        text = f"{value / 1_000_000_000:.2f} M"
    elif value >= 1_000_000:
        text = f"{value / 1_000_000:.1f} jt"
    else:
        text = f"{value:,.0f}".replace(",", ".")
        return f"{sign}Rp{text}"
    return f"{sign}Rp{text.replace('.', ',')}"


def month_label(month: str) -> str:
    year, mm = month.split("-")
    return f"{MONTH_NAMES[mm]} {year}"


def signed_pct(value: float) -> str:
    return f"{value:+.0f}%"


def build_summary(df: pd.DataFrame, weakest: pd.DataFrame) -> str:
    m = months_in(df)
    prev_total = df.loc[df["month"] == m.previous, "net_sales_idr"].sum()
    last_total = df.loc[df["month"] == m.latest, "net_sales_idr"].sum()
    total_change = (last_total - prev_total) / prev_total * 100

    regions = sales_by(df, "region")
    brands = sales_by(df, "brand")
    top_region = regions.index[0]
    growth_region = regions["change_pct"].idxmax()
    drop_region = regions["change_pct"].idxmin()
    top_brand = brands.index[0]
    drop_brand = brands["change_pct"].idxmin()

    growth_driver = _biggest_mover(df, m, "region", growth_region)
    drop_driver = _biggest_mover(df, m, "region", drop_region)

    weak_names = ", ".join(
        f"{row.outlet_name} ({row.branch}, {signed_pct(row.change_pct)})"
        for row in weakest.itertuples()
    )

    text = (
        f"Penjualan bersih {month_label(m.latest)} {rupiah(last_total)}, "
        f"{signed_pct(total_change)} dari {month_label(m.previous)}. "
        f"{top_region} tetap region terbesar ({rupiah(regions.loc[top_region, m.latest])}); "
        f"{growth_region} tumbuh paling cepat ({signed_pct(regions.loc[growth_region, 'change_pct'])}, "
        f"terutama dari {growth_driver}), "
        f"sedangkan {drop_region} turun paling dalam ({signed_pct(regions.loc[drop_region, 'change_pct'])}, "
        f"terbesar di {drop_driver}). "
        f"{top_brand} menyumbang {brands.loc[top_brand, 'share_pct']:.0f}% penjualan; "
        f"{drop_brand} paling melemah ({signed_pct(brands.loc[drop_brand, 'change_pct'])}). "
        f"5 outlet terlemah yang perlu dikunjungi minggu ini: {weak_names}."
    )
    if len(text) > TELEGRAM_MAX_CHARS:
        raise ValueError("Ringkasan melebihi batas 4096 karakter Telegram.")
    return text


def _biggest_mover(df: pd.DataFrame, m, column: str, value: str) -> str:
    """Outlet whose month-on-month change moved this region the most, e.g. 'Grosir X Malang +Rp47,7 jt'."""
    part = df[df[column] == value]
    by_outlet = part.pivot_table(
        index=["outlet_name", "branch"], columns="month", values="net_sales_idr",
        aggfunc="sum", fill_value=0,
    )
    delta = by_outlet.get(m.latest, 0) - by_outlet.get(m.previous, 0)
    name, branch = delta.abs().idxmax()
    change = delta.loc[(name, branch)]
    return f"{name} {branch} {'+' if change >= 0 else ''}{rupiah(change)}"
