"""Aggregations and the weakest-outlet ranking.

Weakest outlet = an outlet that is both shrinking and small for its kind.
Raw lowest sales would only list small warungs, which is not useful to a
sales manager, so each outlet is compared with:
  1. itself: net sales in the latest month vs the month before;
  2. its peers: latest-month net sales vs the median of the same outlet_type.
Each measure is turned into a percentile rank (0 = worst, 1 = best) and the
two ranks are averaged. The 5 lowest averages are flagged.
Outlets with no sales in the earlier month are new; they have no trend yet,
so they are listed separately and never flagged.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

WEAKEST_COUNT = 5


@dataclass(frozen=True)
class Months:
    previous: str
    latest: str


def months_in(df: pd.DataFrame) -> Months:
    months = sorted(df["month"].unique())
    if len(months) < 2:
        raise ValueError("Data perlu minimal 2 bulan untuk menghitung tren outlet.")
    return Months(previous=months[-2], latest=months[-1])


def sales_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Net sales per value of `column`, split by month, sorted by total."""
    table = df.pivot_table(
        index=column, columns="month", values="net_sales_idr", aggfunc="sum", fill_value=0
    )
    months = list(table.columns)
    table["total"] = table[months].sum(axis=1)
    if len(months) >= 2:
        prev, last = months[-2], months[-1]
        table["change_pct"] = _pct_change(table[prev], table[last])
    table["share_pct"] = table["total"] / table["total"].sum() * 100
    return table.sort_values("total", ascending=False)


def region_brand_matrix(df: pd.DataFrame) -> pd.DataFrame:
    return df.pivot_table(
        index="region", columns="brand", values="net_sales_idr", aggfunc="sum", fill_value=0
    )


def outlet_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    """One row per outlet with the measures used to rank weakness."""
    m = months_in(df)
    last_date = df["date"].max()

    info = df.groupby("outlet_id").agg(
        outlet_name=("outlet_name", "first"),
        outlet_type=("outlet_type", "first"),
        region=("region", "first"),
        branch=("branch", "first"),
        salesman=("salesman", lambda s: ", ".join(sorted(s.unique()))),
        last_order=("date", "max"),
        invoices=("invoice_no", "nunique"),
    )
    monthly = df.pivot_table(
        index="outlet_id", columns="month", values="net_sales_idr", aggfunc="sum", fill_value=0
    )
    card = info.join(monthly[[m.previous, m.latest]].rename(
        columns={m.previous: "net_previous", m.latest: "net_latest"}
    ))
    card["days_since_order"] = (last_date - card["last_order"]).dt.days
    card["is_new"] = card["net_previous"] <= 0
    card["change_pct"] = _pct_change(card["net_previous"], card["net_latest"])

    peer_median = card.groupby("outlet_type")["net_latest"].transform("median")
    card["peer_index"] = card["net_latest"] / peer_median

    ranked = ~card["is_new"]
    card["trend_rank"] = card.loc[ranked, "change_pct"].rank(pct=True)
    card["peer_rank"] = card.loc[ranked, "peer_index"].rank(pct=True)
    card["weakness_score"] = (card["trend_rank"] + card["peer_rank"]) / 2
    return card.sort_values("weakness_score")


def weakest_outlets(card: pd.DataFrame, n: int = WEAKEST_COUNT) -> pd.DataFrame:
    weakest = card[~card["is_new"]].nsmallest(n, "weakness_score").copy()
    weakest["reason"] = weakest.apply(_reason, axis=1)
    return weakest


def _reason(row: pd.Series) -> str:
    parts = []
    if row["change_pct"] < 0:
        parts.append(f"turun {abs(row['change_pct']):.0f}% dari bulan lalu")
    else:
        parts.append(f"naik {row['change_pct']:.0f}% dari bulan lalu")
    parts.append(f"hanya {row['peer_index'] * 100:.0f}% dari median {row['outlet_type']}")
    if row["days_since_order"] >= 7:
        parts.append(f"belum order {row['days_since_order']} hari")
    return "; ".join(parts)


def _pct_change(before: pd.Series, after: pd.Series) -> pd.Series:
    return (after - before) / before.where(before > 0) * 100
