"""Telegram bot for the sales dashboard.

The bot is a thin relay: every message text comes from the backend
(/api/messages/<name>), so its numbers always match the dashboard.
Sending reports to recipients also goes through the backend (/api/send).

Commands: /ringkasan /region /brand /terlemah /dashboard /chatid /help
Admins (TELEGRAM_ADMIN_CHAT_IDS): /kirim, to pick who gets their report.
Invite links (t.me/<bot>?start=<code>) connect a recipient to their chat.
Optional daily digest: set TELEGRAM_DIGEST_CHAT_IDS and DIGEST_TIME.
"""

from __future__ import annotations

import logging
import os
from datetime import time
from zoneinfo import ZoneInfo

import httpx
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # the token appears in request URLs
log = logging.getLogger("sales-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API_URL = os.environ.get("API_URL", "http://app:8000").rstrip("/")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip()
TIMEZONE = ZoneInfo(os.environ.get("TZ", "Asia/Jakarta"))
DIGEST_TIME = os.environ.get("DIGEST_TIME", "08:00").strip()


def _ids(name: str) -> set[int]:
    return {int(x) for x in os.environ.get(name, "").replace(" ", "").split(",") if x}


ALLOWED_CHAT_IDS = _ids("TELEGRAM_ALLOWED_CHAT_IDS")  # empty = anyone can use the bot
ADMIN_CHAT_IDS = _ids("TELEGRAM_ADMIN_CHAT_IDS")  # who may send reports with /kirim
DIGEST_CHAT_IDS = _ids("TELEGRAM_DIGEST_CHAT_IDS")

MESSAGE_COMMANDS = {
    "ringkasan": "Ringkasan 1 paragraf untuk sales manager",
    "region": "Penjualan per region",
    "brand": "Penjualan per brand",
    "terlemah": "5 outlet terlemah dan alasannya",
}
OTHER_COMMANDS = {
    "kirim": "Kirim laporan ke sales manager / atasan (admin)",
    "dashboard": "Link ke dashboard web",
    "chatid": "Tampilkan chat ID ini (untuk konfigurasi)",
    "help": "Daftar perintah",
}


async def fetch_text(name: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(f"{API_URL}/api/messages/{name}")
        res.raise_for_status()
        return res.json()["text"]


async def api(method: str, path: str, **kwargs) -> dict | list:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.request(method, f"{API_URL}{path}", **kwargs)
        res.raise_for_status()
        return res.json()


def allowed(update: Update) -> bool:
    chat = update.effective_chat.id
    return not ALLOWED_CHAT_IDS or chat in ALLOWED_CHAT_IDS or chat in ADMIN_CHAT_IDS


def is_admin(update: Update) -> bool:
    return update.effective_chat.id in ADMIN_CHAT_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start <invite code> connects this chat to a recipient; plain /start shows help."""
    if not context.args:
        await help_command(update, context)
        return
    try:
        person = await api("POST", "/api/recipients/register",
                           json={"invite_code": context.args[0], "chat_id": update.effective_chat.id})
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            await update.message.reply_text("Link undangan tidak dikenal. Minta link baru ke admin.")
            return
        raise
    except httpx.HTTPError:
        log.exception("register failed")
        await update.message.reply_text("Belum bisa terhubung. Coba lagi sebentar lagi.")
        return
    scope = f"region {person['region']}" if person["region"] else "seluruh region"
    await update.message.reply_text(
        f"Terhubung sebagai {person['name']} ({person['role_label']}, {scope}). "
        "Laporan penjualan akan dikirim ke chat ini."
    )


def _label(person: dict) -> str:
    return f"{person['name']} · {person['region'] or 'Overall'}"


async def kirim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin picks who gets their report: one person, all managers, or everyone."""
    if not is_admin(update):
        await update.message.reply_text(
            "Hanya admin yang bisa mengirim laporan. Tambahkan chat ID ini "
            f"({update.effective_chat.id}) ke TELEGRAM_ADMIN_CHAT_IDS."
        )
        return
    try:
        people = await api("GET", "/api/recipients")
    except httpx.HTTPError:
        log.exception("listing recipients failed")
        await update.message.reply_text("Daftar penerima belum bisa diambil. Coba lagi sebentar lagi.")
        return
    connected = [p for p in people if p["connected"]]
    waiting = [p for p in people if not p["connected"]]
    if not connected:
        await update.message.reply_text(
            "Belum ada penerima yang terhubung. Bagikan link undangan dari tab 'Kirim Telegram' di dashboard."
        )
        return
    buttons = [[InlineKeyboardButton(_label(p), callback_data=f"send:{p['id']}")] for p in connected]
    buttons.append([InlineKeyboardButton("Semua sales manager", callback_data="send:managers")])
    buttons.append([InlineKeyboardButton("Semua (manager + atasan)", callback_data="send:all")])
    text = "Kirim laporan ke siapa? Manager dapat laporan region-nya, atasan dapat laporan overall."
    if waiting:
        text += "\n\nBelum terhubung: " + ", ".join(_label(p) for p in waiting)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def on_send_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update):
        await query.edit_message_text("Hanya admin yang bisa mengirim laporan.")
        return
    choice = query.data.split(":", 1)[1]
    try:
        people = await api("GET", "/api/recipients")
        if choice == "all":
            ids = [p["id"] for p in people if p["connected"]]
        elif choice == "managers":
            ids = [p["id"] for p in people if p["connected"] and p["role"] == "manager"]
        else:
            ids = [int(choice)]
        result = await api("POST", "/api/send", json={"recipient_ids": ids})
    except httpx.HTTPError:
        log.exception("send failed")
        await query.edit_message_text("Pengiriman gagal. Cek log bot dan backend.")
        return
    lines = [f"Terkirim {result['sent']}, gagal {result['failed']}."]
    lines += [f"- {r['name']}: {'terkirim' if r['ok'] else r['error']}" for r in result["results"]]
    await query.edit_message_text("\n".join(lines))


async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Chat ini belum diizinkan. Minta admin menambahkan chat ID ke konfigurasi bot.")
        return
    name = update.message.text.split()[0].lstrip("/").split("@")[0]
    try:
        await update.message.reply_text(await fetch_text(name))
    except httpx.HTTPError:
        log.exception("backend request failed for /%s", name)
        await update.message.reply_text("Data belum bisa diambil. Coba lagi sebentar lagi.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["Bot penjualan. Perintah:"]
    lines += [f"/{cmd} - {desc}" for cmd, desc in {**MESSAGE_COMMANDS, **OTHER_COMMANDS}.items()]
    if DIGEST_CHAT_IDS:
        lines.append(f"Ringkasan otomatis dikirim tiap hari pukul {DIGEST_TIME}.")
    await update.message.reply_text("\n".join(lines))


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = DASHBOARD_URL or "DASHBOARD_URL belum diisi di konfigurasi."
    await update.message.reply_text(text)


async def send_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        text = await fetch_text("ringkasan")
    except httpx.HTTPError:
        log.exception("digest: backend request failed")
        return
    for chat_id in DIGEST_CHAT_IDS:
        try:
            await context.bot.send_message(chat_id, text)
        except Exception:  # one bad chat must not stop the others
            log.exception("digest: send to %s failed", chat_id)


async def on_startup(app: Application) -> None:
    commands = {**MESSAGE_COMMANDS, **OTHER_COMMANDS}
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in commands.items()])
    me = await app.bot.get_me()
    log.info("bot @%s ready; backend %s; allowed chats: %s; admins: %s",
             me.username, API_URL, ALLOWED_CHAT_IDS or "all", ADMIN_CHAT_IDS or "none")


def main() -> None:
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN kosong. Isi di file .env lalu jalankan ulang.")

    app = Application.builder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler(list(MESSAGE_COMMANDS), reply_message))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("kirim", kirim))
    app.add_handler(CallbackQueryHandler(on_send_choice, pattern=r"^send:"))
    app.add_handler(CommandHandler("chatid", chatid))
    app.add_handler(CommandHandler("dashboard", dashboard))

    if DIGEST_CHAT_IDS:
        hour, minute = (int(x) for x in DIGEST_TIME.split(":"))
        app.job_queue.run_daily(send_digest, time(hour, minute, tzinfo=TIMEZONE))
        log.info("daily digest at %s %s to %s", DIGEST_TIME, TIMEZONE, DIGEST_CHAT_IDS)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
