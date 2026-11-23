import pytest
from fastapi.testclient import TestClient

from api import DEFAULT_CSV, app

client = TestClient(app)


def test_dashboard_returns_all_sections():
    body = client.get("/api/dashboard").json()
    assert body["months"]["latest"] == "2026-10"
    assert len(body["weakest"]) == 5
    assert all(w["reason"] for w in body["weakest"])
    assert sum(r["total"] for r in body["by_region"]) == sum(b["total"] for b in body["by_brand"])
    assert body["data_quality"]["duplicate_rows_removed"] == 3
    assert body["summary"].startswith("Penjualan bersih Oktober 2026")


def test_region_filter_changes_totals_but_not_weakest():
    full = client.get("/api/dashboard").json()
    jabar = client.get("/api/dashboard", params={"region": "Jawa Barat"}).json()
    assert [r["region"] for r in jabar["by_region"]] == ["Jawa Barat"]
    assert jabar["kpi"]["net_latest"] < full["kpi"]["net_latest"]
    assert [w["outlet_id"] for w in jabar["weakest"]] == [w["outlet_id"] for w in full["weakest"]]


def test_unknown_region_is_404():
    assert client.get("/api/dashboard", params={"region": "Papua"}).status_code == 404


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_bot_messages_fit_telegram_and_match_dashboard():
    dash = client.get("/api/dashboard").json()
    for name in client.get("/api/messages").json():
        text = client.get(f"/api/messages/{name}").json()["text"]
        assert 0 < len(text) <= 4096
    assert client.get("/api/messages/ringkasan").json()["text"] == dash["summary"]
    weakest = client.get("/api/messages/terlemah").json()["text"]
    assert all(w["outlet_id"] in weakest for w in dash["weakest"])
    assert client.get("/api/messages/nope").status_code == 404


def test_frontend_is_served_when_built(tmp_path):
    from fastapi import FastAPI

    from api import mount_frontend

    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<div id=root></div>")
    web = FastAPI()
    assert mount_frontend(web, tmp_path)
    web_client = TestClient(web)
    assert web_client.get("/").text == "<div id=root></div>"
    assert web_client.get("/any/page").text == "<div id=root></div>"  # client-side routes fall back
    assert web_client.get("/assets/app.js").text == "console.log(1)"


def test_frontend_is_skipped_when_not_built(tmp_path):
    from fastapi import FastAPI

    from api import mount_frontend

    assert not mount_frontend(FastAPI(), tmp_path)


class FakeTelegram:
    configured = True

    def __init__(self, fail_for=()):
        self.sent = []
        self.fail_for = set(fail_for)

    def bot_username(self):
        return "dk_sales_bot"

    def send(self, chat_id, text):
        from sales.telegram import TelegramError

        if chat_id in self.fail_for:
            raise TelegramError("Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, text))


@pytest.fixture
def fake_telegram(monkeypatch):
    import api

    fake = FakeTelegram(fail_for={999})
    monkeypatch.setattr(api, "telegram", fake)
    return fake


@pytest.fixture
def people(tmp_path, monkeypatch):
    """Fresh recipient table with a Jawa Barat manager, a Sumatera manager and a head."""
    import api
    from sales.recipients import RecipientStore

    store = RecipientStore(tmp_path / "people.db")
    monkeypatch.setattr(api, "recipients", store)
    regions = api._regions()
    return {
        "jabar": store.add("Pak Jabar", "manager", "Jawa Barat", regions, chat_id=111),
        "sumatera": store.add("Bu Sumatera", "manager", "Sumatera", regions),  # not connected
        "head": store.add("Bu Kepala", "head", None, regions, chat_id=222),
        "blocked": store.add("Pak Blokir", "manager", "Kalimantan", regions, chat_id=999),
        "store": store,
    }


def test_patch_recipient_sets_and_clears_chat_id(people):
    rid = people["sumatera"].id
    body = client.patch(f"/api/recipients/{rid}", json={"chat_id": -100123}).json()
    assert body["chat_id"] == -100123 and body["connected"]
    body = client.patch(f"/api/recipients/{rid}", json={"name": "Bu Sumatera Baru"}).json()
    assert body["chat_id"] == -100123  # untouched when not sent
    body = client.patch(f"/api/recipients/{rid}", json={"chat_id": None}).json()
    assert body["chat_id"] is None and not body["connected"]


def test_patch_recipient_validation(people):
    rid = people["jabar"].id
    assert client.patch(f"/api/recipients/{rid}", json={"region": "Papua"}).status_code == 422
    assert client.patch(f"/api/recipients/{rid}", json={"chat_id": "abc"}).status_code == 422
    assert client.patch("/api/recipients/9999", json={"name": "x"}).status_code == 404


def test_add_recipient_with_chat_id_is_ready_to_send(people):
    body = client.post("/api/recipients", json={"name": "Pak Langsung", "region": "Jawa Timur", "chat_id": 555}).json()
    assert body["connected"]


def test_telegram_status_reports_recipients_file():
    body = client.get("/api/telegram").json()
    assert body["recipients_file"]["name"].endswith(".csv")
    assert {"added", "updated", "skipped"} <= set(body["recipients_file"])


def test_recipient_list_has_invite_links(people, fake_telegram):
    body = client.get("/api/recipients").json()
    jabar = next(r for r in body if r["name"] == "Pak Jabar")
    assert jabar["invite_link"] == f"https://t.me/dk_sales_bot?start={jabar['invite_code']}"
    assert jabar["connected"] and jabar["role_label"] == "Sales Manager"


def test_invite_link_is_empty_without_bot(people):
    assert all(r["invite_link"] is None for r in client.get("/api/recipients").json())


def test_add_and_delete_recipient(people):
    res = client.post("/api/recipients", json={"name": "Pak Baru", "role": "manager", "region": "Jawa Timur"})
    assert res.status_code == 201
    new_id = res.json()["id"]
    assert client.delete(f"/api/recipients/{new_id}").status_code == 204
    assert client.delete(f"/api/recipients/{new_id}").status_code == 404


def test_add_recipient_rejects_unknown_region(people):
    res = client.post("/api/recipients", json={"name": "X", "role": "manager", "region": "Papua"})
    assert res.status_code == 422
    assert "Region tidak dikenal" in res.json()["detail"]


def test_register_via_invite_code(people):
    code = people["sumatera"].invite_code
    res = client.post("/api/recipients/register", json={"invite_code": code, "chat_id": 333})
    assert res.json()["connected"] is True
    assert client.post("/api/recipients/register", json={"invite_code": "nope", "chat_id": 1}).status_code == 404


def test_preview_matches_role(people):
    manager = client.get(f"/api/recipients/{people['jabar'].id}/preview").json()["text"]
    head = client.get(f"/api/recipients/{people['head'].id}/preview").json()["text"]
    assert manager.startswith("Laporan region Jawa Barat")
    assert head.startswith("Penjualan bersih")
    assert client.get("/api/recipients/9999/preview").status_code == 404


def test_preview_for_region_missing_from_data(people):
    store = people["store"]
    ghost = store.add("Pak Hantu", "manager", "Papua", ["Papua"])
    assert client.get(f"/api/recipients/{ghost.id}/preview").status_code == 422


def test_send_reports_each_recipient_their_own_report(people, fake_telegram):
    ids = [people[k].id for k in ("jabar", "sumatera", "head", "blocked")] + [people["jabar"].id]
    body = client.post("/api/send", json={"recipient_ids": ids}).json()
    assert (body["sent"], body["failed"]) == (2, 2)  # the repeated id is sent once
    by_name = {r["name"]: r for r in body["results"]}
    assert "belum lengkap" in by_name["Bu Sumatera"]["error"]
    assert "blocked" in by_name["Pak Blokir"]["error"]

    sent = dict(fake_telegram.sent)
    assert sent[111].startswith("Laporan region Jawa Barat")
    assert sent[222].startswith("Penjualan bersih")

    listed = {r["name"]: r for r in client.get("/api/recipients").json()}
    assert listed["Pak Jabar"]["last_send_ok"] is True
    assert listed["Pak Blokir"]["last_send_ok"] is False


def test_send_to_region_missing_from_data_is_reported(people, fake_telegram):
    ghost = people["store"].add("Pak Hantu", "manager", "Papua", ["Papua"], chat_id=444)
    body = client.post("/api/send", json={"recipient_ids": [ghost.id]}).json()
    assert "tidak ada di data" in body["results"][0]["error"]


def test_send_without_bot_token_is_503(people):
    assert client.post("/api/send", json={"recipient_ids": [people["jabar"].id]}).status_code == 503


def test_send_to_unknown_recipient_is_404(people, fake_telegram):
    assert client.post("/api/send", json={"recipient_ids": [9999]}).status_code == 404


def test_telegram_status(fake_telegram):
    body = client.get("/api/telegram").json()
    assert (body["configured"], body["bot_username"]) == (True, "dk_sales_bot")


def test_dataset_needs_two_months(tmp_path):
    from api import Dataset
    from sales.storage import Store

    with open(DEFAULT_CSV, encoding="utf-8") as f:
        september = "".join(f.readlines()[:400])
    one_month = tmp_path / "sep.csv"
    one_month.write_text(september, encoding="utf-8")
    with pytest.raises(ValueError, match="minimal 2 bulan"):
        Dataset(Store(tmp_path / "s.db"), one_month)


def test_dataset_is_seeded_on_first_setup_only(tmp_path, monkeypatch):
    import shutil

    import sales.seed
    from api import Dataset
    from sales.storage import Store

    csv_copy = tmp_path / "sales.csv"
    shutil.copy(DEFAULT_CSV, csv_copy)
    store = Store(tmp_path / "s.db")
    first = Dataset(store, csv_copy)
    assert first.seeded and first.seeded_at

    def must_not_parse(_path):
        raise AssertionError("CSV parsed again on a later start")

    monkeypatch.setattr(sales.seed, "load_sales", must_not_parse)
    second = Dataset(store, csv_copy)  # container restarted, same volume
    assert not second.seeded
    assert second.seeded_at == first.seeded_at
    assert second.df["net_sales_idr"].sum() == first.df["net_sales_idr"].sum()


def test_changed_csv_is_reported_not_reseeded(tmp_path):
    from api import Dataset
    from sales.storage import Store

    lines = DEFAULT_CSV.read_text(encoding="utf-8").splitlines(keepends=True)
    csv_file = tmp_path / "sales.csv"
    csv_file.write_text("".join(lines), encoding="utf-8")
    store = Store(tmp_path / "s.db")
    first = Dataset(store, csv_file)
    csv_file.write_text("".join(lines[:-100]), encoding="utf-8")  # file edited after setup
    again = Dataset(store, csv_file)
    assert not again.seeded
    assert again.csv_changed
    assert len(again.df) == len(first.df)  # still the seeded data


def test_health_reports_seed_state():
    body = client.get("/api/health").json()
    assert body["seeded_at"]
    assert body["csv_changed_since_seed"] is False
