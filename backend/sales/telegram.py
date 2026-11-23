"""Minimal Telegram Bot API client used by the backend to send reports.

The backend sends; the bot container only receives commands. Both use the
same token. Kept small on purpose and replaceable in tests.
"""

from __future__ import annotations

import httpx

API = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self.token = token.strip()
        self.http = http or httpx.Client(timeout=15)
        self._username: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _call(self, method: str, **payload) -> dict:
        if not self.configured:
            raise TelegramError("TELEGRAM_BOT_TOKEN belum diisi.")
        try:
            res = self.http.post(f"{API}/bot{self.token}/{method}", json=payload)
            body = res.json()
        except (httpx.HTTPError, ValueError) as err:
            # Never include the request URL: it contains the token.
            raise TelegramError(f"Telegram tidak bisa dihubungi ({type(err).__name__}).") from None
        if not body.get("ok"):
            raise TelegramError(body.get("description", "Telegram menolak permintaan."))
        return body["result"]

    def bot_username(self) -> str | None:
        if self._username is None and self.configured:
            try:
                self._username = self._call("getMe")["username"]
            except TelegramError:
                return None
        return self._username

    def send(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)
