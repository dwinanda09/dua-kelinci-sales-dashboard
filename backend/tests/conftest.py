import os
import tempfile

import pandas as pd
import pytest

# Keep tests away from the real database file.
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
# Never reach the real Telegram from tests; tests that send use a fake client.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
# The API imports recipients from this file at startup; a missing file means none.
os.environ.setdefault("RECIPIENTS_CSV", os.path.join(tempfile.mkdtemp(), "no-recipients.csv"))

from sales.clean import EXPECTED_COLUMNS, clean_sales  # noqa: E402


def sales_line(date, outlet_id, outlet_type, region, brand, net, name=None, invoice=None):
    """One clean invoice line where qty x price = gross = net (no discount)."""
    return {
        "date": date, "invoice_no": invoice or f"INV-{outlet_id}-{date}-{brand}", "region": region,
        "branch": f"Cabang {region}", "outlet_id": outlet_id, "outlet_name": name or f"Outlet {outlet_id}",
        "outlet_type": outlet_type, "salesman": "Andi", "brand": brand, "sku": f"{brand} 100g",
        "qty_carton": "1", "price_per_carton_idr": str(net), "gross_sales_idr": str(net),
        "discount_idr": "0", "net_sales_idr": str(net),
    }


def make_sales(lines):
    df, _ = clean_sales(pd.DataFrame(lines, columns=EXPECTED_COLUMNS))
    return df


@pytest.fixture
def small_sales():
    """Six outlets with numbers small enough to check every score by hand.

    Net sales Sep -> Oct:
      A  Toko Kelontong  Jawa Barat   100 -> 100   (0%)
      B  Toko Kelontong  Jawa Barat   100 ->  50   (-50%)
      C  Toko Kelontong  Sumatera     100 -> 150   (+50%, Tos Tos, orders on 31 Oct)
      D  Toko Kelontong  Sumatera       0 ->  80   (new outlet)
      G1 Grosir          Jabodetabek 1000 -> 500   (-50%)
      G2 Grosir          Jabodetabek 1000 -> 1100  (+10%)
    """
    sep, octo = "2026-09-10", "2026-10-01"
    return make_sales([
        sales_line(sep, "A", "Toko Kelontong", "Jawa Barat", "Sukro", 100, "Toko A"),
        sales_line(octo, "A", "Toko Kelontong", "Jawa Barat", "Sukro", 100, "Toko A"),
        sales_line(sep, "B", "Toko Kelontong", "Jawa Barat", "Sukro", 100, "Toko B"),
        sales_line(octo, "B", "Toko Kelontong", "Jawa Barat", "Sukro", 50, "Toko B"),
        sales_line(sep, "C", "Toko Kelontong", "Sumatera", "Tos Tos", 100, "Toko C"),
        sales_line("2026-10-31", "C", "Toko Kelontong", "Sumatera", "Tos Tos", 150, "Toko C"),
        sales_line(octo, "D", "Toko Kelontong", "Sumatera", "Sukro", 80, "Toko D"),
        sales_line(sep, "G1", "Grosir", "Jabodetabek", "Sukro", 1000, "Grosir G1"),
        sales_line(octo, "G1", "Grosir", "Jabodetabek", "Sukro", 500, "Grosir G1"),
        sales_line(sep, "G2", "Grosir", "Jabodetabek", "Sukro", 1000, "Grosir G2"),
        sales_line(octo, "G2", "Grosir", "Jabodetabek", "Sukro", 1100, "Grosir G2"),
    ])
