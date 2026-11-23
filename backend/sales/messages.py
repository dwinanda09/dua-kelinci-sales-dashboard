"""Plain-text messages for the Telegram bot.

Built here, next to the analysis, so the bot only relays text and every
number matches the dashboard.
"""

from __future__ import annotations

import pandas as pd

from .analysis import months_in, outlet_scorecard, sales_by, weakest_outlets
from .summary import build_summary, month_label, rupiah, signed_pct

COMMANDS = {
    "ringkasan": "Ringkasan 1 paragraf untuk sales manager",
    "region": "Penjualan per region",
    "brand": "Penjualan per brand",
    "terlemah": "5 outlet terlemah dan alasannya",
}


def build_message(name: str, df: pd.DataFrame) -> str:
    if name == "ringkasan":
        return build_summary(df, weakest_outlets(outlet_scorecard(df)))
    if name in ("region", "brand"):
        return _breakdown(df, name)
    if name == "terlemah":
        return _weakest(df)
    raise KeyError(name)


def _breakdown(df: pd.DataFrame, column: str) -> str:
    m = months_in(df)
    table = sales_by(df, column).sort_values(m.latest, ascending=False)
    title = "region" if column == "region" else "brand"
    lines = [f"Penjualan per {title}, {month_label(m.latest)} (vs {month_label(m.previous)}):"]
    for i, (name, row) in enumerate(table.iterrows(), start=1):
        change = "baru" if pd.isna(row["change_pct"]) else signed_pct(row["change_pct"])
        lines.append(f"{i}. {name}: {rupiah(row[m.latest])} ({change})")
    total_prev = table[m.previous].sum()
    total_last = table[m.latest].sum()
    lines.append(f"Total: {rupiah(total_last)} ({signed_pct((total_last - total_prev) / total_prev * 100)})")
    return "\n".join(lines)


def _weakest(df: pd.DataFrame) -> str:
    m = months_in(df)
    weakest = weakest_outlets(outlet_scorecard(df))
    lines = [f"5 outlet terlemah ({month_label(m.latest)}):"]
    lines += _outlet_lines(weakest)
    return "\n".join(lines)


def _outlet_lines(outlets: pd.DataFrame) -> list[str]:
    return [
        f"{i}. {row.outlet_name} ({row.Index}, {row.branch}), salesman {row.salesman}\n"
        f"   {rupiah(row.net_previous)} -> {rupiah(row.net_latest)}; {row.reason}"
        for i, row in enumerate(outlets.itertuples(), start=1)
    ]


REGION_WATCHLIST = 3  # outlets listed in a region manager's report


def region_report(df: pd.DataFrame, region: str) -> str:
    """Report for the sales manager of one region."""
    m = months_in(df)
    regions = sales_by(df, "region").sort_values(m.latest, ascending=False)
    if region not in regions.index:
        raise KeyError(region)
    part = df[df["region"] == region]
    row = regions.loc[region]
    rank = regions.index.get_loc(region) + 1

    lines = [
        f"Laporan region {region}, {month_label(m.latest)}",
        f"Penjualan bersih {rupiah(row[m.latest])}, {_change(row['change_pct'])} dari {month_label(m.previous)} "
        f"(peringkat {rank} dari {len(regions)} region).",
        "",
        "Per cabang:",
    ]
    branches = sales_by(part, "branch").sort_values(m.latest, ascending=False)
    lines += [f"- {name}: {rupiah(b[m.latest])} ({_change(b['change_pct'])})" for name, b in branches.iterrows()]

    brands = sales_by(part, "brand").sort_values(m.latest, ascending=False)
    top = ", ".join(f"{name} {rupiah(b[m.latest])} ({_change(b['change_pct'])})" for name, b in brands.head(3).iterrows())
    lines += ["", f"Brand terbesar: {top}."]
    falling = brands["change_pct"].dropna()
    if not falling.empty and falling.min() < 0:
        lines.append(f"Brand paling melemah: {falling.idxmin()} ({signed_pct(falling.min())}).")

    # Scores come from all outlets nationally, so a region's list is comparable across managers.
    card = outlet_scorecard(df)
    in_region = card[card["region"] == region]
    watch = weakest_outlets(in_region, n=REGION_WATCHLIST)
    if not watch.empty:
        lines += ["", f"Outlet yang perlu dikunjungi ({len(watch)} terlemah di region ini):"]
        lines += _outlet_lines(watch)
    new = in_region[in_region["is_new"]]
    if not new.empty:
        lines += ["", "Outlet baru: " + ", ".join(f"{r.outlet_name} ({r.branch})" for r in new.itertuples()) + "."]
    return "\n".join(lines)


def overall_report(df: pd.DataFrame) -> str:
    """Report for the head of sales: the national summary plus every region."""
    summary = build_summary(df, weakest_outlets(outlet_scorecard(df)))
    return f"{summary}\n\n{_breakdown(df, 'region')}"


def report_for(role: str, region: str | None, df: pd.DataFrame) -> str:
    return region_report(df, region) if role == "manager" else overall_report(df)


def _change(value: float) -> str:
    return "baru" if pd.isna(value) else signed_pct(value)
