"""HTTP API over the sales analysis, plus the built React app.

Run: uvicorn api:app --port 8000   (from the backend/ folder)
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sales.analysis import months_in, outlet_scorecard, region_brand_matrix, sales_by, weakest_outlets
from sales.messages import COMMANDS, build_message, report_for
from sales.recipients import Recipient, RecipientError, RecipientStore
from sales.seed import seed_if_empty
from sales.storage import Store
from sales.summary import build_summary, month_label
from sales.telegram import TelegramClient, TelegramError

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = Path(os.getenv("SALES_CSV", ROOT / "data" / "sales.csv"))
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "var" / "sales.db"))
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", ROOT / "frontend" / "dist"))
RECIPIENTS_CSV = Path(os.getenv("RECIPIENTS_CSV", ROOT / "config" / "recipients.csv"))

log = logging.getLogger("uvicorn.error")  # shows up in `docker compose logs app`
app = FastAPI(title="Sales Dashboard API")


class Dataset:
    """The static sales data, served from SQLite.

    Seeded from data/sales.csv only on first setup (empty database). After
    that every start reads the saved copy; to load a changed CSV, run the
    seeder (./setup.sh reseed). There is no upload.
    """

    def __init__(self, store: Store, csv_path: Path) -> None:
        result = seed_if_empty(store, csv_path)
        self.df, self.report, self.source = result.saved.df, result.saved.report, result.saved.source
        self.seeded_at = result.saved.seeded_at
        self.seeded = result.seeded
        self.csv_changed = result.csv_changed
        if result.seeded:
            log.info("first setup: seeded %d rows from %s", len(self.df), csv_path.name)
        if result.csv_changed:
            log.warning("%s changed since it was seeded; still serving the saved data. "
                        "Run ./setup.sh reseed to load the new file.", csv_path.name)


dataset = Dataset(Store(DB_PATH), DEFAULT_CSV)
recipients = RecipientStore(DB_PATH)
recipients_import = recipients.import_csv(RECIPIENTS_CSV, sorted(dataset.df["region"].unique()))
for problem in recipients_import.skipped:
    log.warning("%s: %s", RECIPIENTS_CSV.name, problem)
telegram = TelegramClient(os.getenv("TELEGRAM_BOT_TOKEN", ""))


class NewRecipient(BaseModel):
    name: str
    role: str = "manager"
    region: str | None = None
    chat_id: int | None = None


class RecipientChange(BaseModel):
    name: str | None = None
    region: str | None = None
    chat_id: int | None = None  # send null to clear


class Registration(BaseModel):
    invite_code: str
    chat_id: int


class SendRequest(BaseModel):
    recipient_ids: list[int]


def _regions() -> list[str]:
    return sorted(dataset.df["region"].unique())


def _recipient_dict(r: Recipient) -> dict:
    username = telegram.bot_username()
    link = f"https://t.me/{username}?start={r.invite_code}" if username else None
    return {**r.as_dict(), "invite_link": link}


@app.get("/api/telegram")
def telegram_status() -> dict:
    return {
        "configured": telegram.configured,
        "bot_username": telegram.bot_username(),
        "recipients_file": {"name": RECIPIENTS_CSV.name, **asdict(recipients_import)},
    }


@app.get("/api/recipients")
def list_recipients() -> list[dict]:
    return [_recipient_dict(r) for r in recipients.list()]


@app.post("/api/recipients", status_code=201)
def add_recipient(body: NewRecipient) -> dict:
    try:
        r = recipients.add(body.name, body.role, body.region, _regions(), body.chat_id)
    except RecipientError as err:
        raise HTTPException(422, str(err)) from err
    return _recipient_dict(r)


@app.patch("/api/recipients/{recipient_id}")
def change_recipient(recipient_id: int, body: RecipientChange) -> dict:
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    try:
        r = recipients.update(_get_recipient(recipient_id).id, _regions(), **changes)
    except RecipientError as err:
        raise HTTPException(422, str(err)) from err
    return _recipient_dict(r)


@app.delete("/api/recipients/{recipient_id}", status_code=204)
def delete_recipient(recipient_id: int) -> None:
    try:
        recipients.delete(recipient_id)
    except KeyError:
        raise HTTPException(404, "Penerima tidak ditemukan.") from None


@app.post("/api/recipients/register")
def register_recipient(body: Registration) -> dict:
    """Called by the bot when someone opens an invite link."""
    try:
        r = recipients.register(body.invite_code, body.chat_id)
    except KeyError:
        raise HTTPException(404, "Kode undangan tidak dikenal.") from None
    return _recipient_dict(r)


@app.get("/api/recipients/{recipient_id}/preview")
def preview_report(recipient_id: int) -> dict:
    r = _get_recipient(recipient_id)
    try:
        return {"recipient_id": r.id, "text": report_for(r.role, r.region, dataset.df)}
    except KeyError:
        raise HTTPException(422, f"Region {r.region} tidak ada di data saat ini.") from None


@app.post("/api/send")
def send_reports(body: SendRequest) -> dict:
    """Send each recipient the report for their role and region."""
    if not telegram.configured:
        raise HTTPException(503, "Bot Telegram belum dikonfigurasi (TELEGRAM_BOT_TOKEN kosong).")
    results = []
    for recipient_id in dict.fromkeys(body.recipient_ids):  # ignore repeated ids, keep order
        r = _get_recipient(recipient_id)
        error = None
        if not r.connected:
            error = "Data belum lengkap: chat ID Telegram kosong. Isi chat ID atau kirim link undangan."
        else:
            try:
                telegram.send(r.chat_id, report_for(r.role, r.region, dataset.df))
            except KeyError:
                error = f"Region {r.region} tidak ada di data saat ini."
            except TelegramError as err:
                error = str(err)
        recipients.log_send(r.id, error is None, error)
        results.append({"recipient_id": r.id, "name": r.name, "ok": error is None, "error": error})
    return {"sent": sum(x["ok"] for x in results), "failed": sum(not x["ok"] for x in results), "results": results}


def _get_recipient(recipient_id: int) -> Recipient:
    try:
        return recipients.get(recipient_id)
    except KeyError:
        raise HTTPException(404, f"Penerima {recipient_id} tidak ditemukan.") from None


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "rows": len(dataset.df),
        "source": dataset.source,
        "seeded_at": dataset.seeded_at,
        "csv_changed_since_seed": dataset.csv_changed,
    }


@app.get("/api/messages")
def message_list() -> dict:
    return COMMANDS


@app.get("/api/messages/{name}")
def message(name: str) -> dict:
    """Ready-to-send plain text for the Telegram bot."""
    if name not in COMMANDS:
        raise HTTPException(404, f"Pesan tidak dikenal: {name}")
    return {"name": name, "text": build_message(name, dataset.df)}


@app.get("/api/dashboard")
def dashboard(region: list[str] = Query(default=[])) -> dict:
    df = dataset.df
    m = months_in(df)
    view = df[df["region"].isin(region)] if region else df
    if view.empty:
        raise HTTPException(404, "Tidak ada data untuk region yang dipilih.")

    # The weakest ranking and the summary always use all outlets,
    # so the flagged 5 do not change when the region filter changes.
    card = outlet_scorecard(df)
    weakest = weakest_outlets(card)

    prev_total = int(view.loc[view["month"] == m.previous, "net_sales_idr"].sum())
    last_total = int(view.loc[view["month"] == m.latest, "net_sales_idr"].sum())

    return {
        "source": dataset.source,
        "months": {"previous": m.previous, "latest": m.latest,
                   "previous_label": month_label(m.previous), "latest_label": month_label(m.latest)},
        "regions": sorted(df["region"].unique().tolist()),
        "kpi": {
            "net_previous": prev_total,
            "net_latest": last_total,
            "change_pct": _num((last_total - prev_total) / prev_total * 100) if prev_total else None,
            "active_outlets": int(view["outlet_id"].nunique()),
            "invoices": int(view["invoice_no"].nunique()),
        },
        "by_region": _breakdown(sales_by(view, "region"), m, "region"),
        "by_brand": _breakdown(sales_by(view, "brand"), m, "brand"),
        "region_brand": _matrix(region_brand_matrix(view)),
        "weakest": _outlets(weakest, with_reason=True),
        "new_outlets": _outlets(card[card["is_new"]]),
        "scorecard": _outlets(card),
        "summary": build_summary(df, weakest),
        "data_quality": {**asdict(dataset.report), "lines": dataset.report.as_lines()},
        "returns": [
            {"date": r.date.strftime("%Y-%m-%d"), "invoice_no": r.invoice_no, "outlet_name": r.outlet_name,
             "sku": r.sku, "qty_carton": int(r.qty_carton), "net_sales_idr": int(r.net_sales_idr)}
            for r in df[df["is_return"]].itertuples()
        ],
    }


def _breakdown(table: pd.DataFrame, m, key: str) -> list[dict]:
    return [
        {key: name, "net_previous": int(row[m.previous]), "net_latest": int(row[m.latest]),
         "total": int(row["total"]), "change_pct": _num(row["change_pct"]), "share_pct": _num(row["share_pct"])}
        for name, row in table.iterrows()
    ]


def _matrix(matrix: pd.DataFrame) -> dict:
    return {
        "brands": matrix.columns.tolist(),
        "rows": [{"region": region, "values": [int(v) for v in row]} for region, row in matrix.iterrows()],
    }


def _outlets(card: pd.DataFrame, with_reason: bool = False) -> list[dict]:
    rows = []
    for outlet_id, r in card.iterrows():
        item = {
            "outlet_id": outlet_id, "outlet_name": r["outlet_name"], "outlet_type": r["outlet_type"],
            "region": r["region"], "branch": r["branch"], "salesman": r["salesman"],
            "net_previous": int(r["net_previous"]), "net_latest": int(r["net_latest"]),
            "change_pct": _num(r["change_pct"]), "peer_index": _num(r["peer_index"]),
            "weakness_score": _num(r["weakness_score"]), "days_since_order": int(r["days_since_order"]),
            "is_new": bool(r["is_new"]),
        }
        if with_reason:
            item["reason"] = r["reason"]
        rows.append(item)
    return rows


def _num(value) -> float | None:
    """Round for JSON; NaN (no previous month) becomes null."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), 2)


def mount_frontend(target: FastAPI, dist: Path) -> bool:
    """Serve the built React app (npm run build in frontend/) if it exists."""
    if not (dist / "index.html").exists():
        return False
    target.mount("/assets", StaticFiles(directory=dist / "assets", check_dir=False), name="assets")

    @target.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        return FileResponse(dist / "index.html")

    return True


mount_frontend(app, FRONTEND_DIST)
