import json

import httpx
import pytest

from sales.telegram import TelegramClient, TelegramError


def client_with(handler):
    return TelegramClient("123:SECRET", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_send_posts_plain_text_to_chat():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    client_with(handler).send(42, "halo")
    assert seen["path"] == "/bot123:SECRET/sendMessage"
    assert seen["body"]["chat_id"] == 42
    assert seen["body"]["text"] == "halo"
    assert "parse_mode" not in seen["body"]  # plain text: no Markdown escaping problems


def test_telegram_refusal_is_reported():
    client = client_with(lambda r: httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"}))
    with pytest.raises(TelegramError, match="blocked"):
        client.send(42, "halo")


def test_network_error_message_does_not_leak_token():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(TelegramError) as err:
        client_with(handler).send(42, "halo")
    assert "SECRET" not in str(err.value)


def test_not_configured():
    client = TelegramClient("  ")
    assert not client.configured
    assert client.bot_username() is None
    with pytest.raises(TelegramError, match="belum diisi"):
        client.send(1, "x")


def test_bot_username_is_cached_and_failure_returns_none():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"ok": True, "result": {"username": "dk_sales_bot"}})

    client = client_with(handler)
    assert client.bot_username() == "dk_sales_bot"
    assert client.bot_username() == "dk_sales_bot"
    assert len(calls) == 1

    bad = client_with(lambda r: httpx.Response(401, json={"ok": False, "description": "Unauthorized"}))
    assert bad.bot_username() is None
