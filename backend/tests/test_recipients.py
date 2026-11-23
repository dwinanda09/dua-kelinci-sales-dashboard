import pytest

from sales.recipients import RecipientError, RecipientStore

REGIONS = ["Jawa Barat", "Sumatera"]


@pytest.fixture
def store(tmp_path):
    return RecipientStore(tmp_path / "r.db")


def write_csv(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_import_adds_any_number_of_people(store, tmp_path):
    f = write_csv(tmp_path / "r.csv", (
        "name,role,region,chat_id\n"
        "Pak Jabar,manager,Jawa Barat,111\n"
        "Pak Jabar 2,manager,Jawa Barat,\n"  # two managers for one region is fine
        "Bu Sumatera,manager,Sumatera,-100222\n"
        "Bu Kepala,head,,333\n"
        "\n"
        "# comment row,,,\n"
    ))
    result = store.import_csv(f, REGIONS)
    assert (result.added, result.updated, result.skipped) == (4, 0, [])
    people = {p.name: p for p in store.list()}
    assert people["Pak Jabar"].chat_id == 111
    assert not people["Pak Jabar 2"].connected  # placeholder: no chat ID yet
    assert people["Bu Sumatera"].chat_id == -100222  # group chat
    assert people["Bu Kepala"].role == "head" and people["Bu Kepala"].region is None


def test_import_again_updates_without_duplicates_and_keeps_invite_chat(store, tmp_path):
    f = write_csv(tmp_path / "r.csv", "name,role,region,chat_id\nPak Jabar,manager,Jawa Barat,\n")
    store.import_csv(f, REGIONS)
    pak = store.list()[0]
    store.register(pak.invite_code, 999)  # linked through an invite link
    write_csv(f, "name,role,region,chat_id\nPak Jabar,manager,Sumatera,\n")
    result = store.import_csv(f, REGIONS)
    assert (result.added, result.updated) == (0, 1)
    pak = store.list()[0]
    assert (pak.region, pak.chat_id) == ("Sumatera", 999)  # empty cell keeps the linked chat
    write_csv(f, "name,role,region,chat_id\nPak Jabar,manager,Sumatera,777\n")
    store.import_csv(f, REGIONS)
    assert store.list()[0].chat_id == 777  # a chat ID in the file wins


def test_import_skips_bad_rows_and_reports_them(store, tmp_path):
    f = write_csv(tmp_path / "r.csv", (
        "name,role,region,chat_id\n"
        "Pak Papua,manager,Papua,1\n"
        "Pak Huruf,manager,Sumatera,abc\n"
        ",manager,Sumatera,2\n"
        "Pak OK,manager,Sumatera,3\n"
    ))
    result = store.import_csv(f, REGIONS)
    assert result.added == 1
    assert len(result.skipped) == 3
    assert result.skipped[0].startswith("baris 2: Region tidak dikenal")
    assert "chat_id harus angka" in result.skipped[1]


def test_import_missing_file_does_nothing(store, tmp_path):
    result = store.import_csv(tmp_path / "none.csv", REGIONS)
    assert (result.added, result.updated, store.list()) == (0, 0, [])


def test_update_changes_fields_and_validates(store):
    r = store.add("Budi", "manager", "Sumatera", REGIONS)
    r = store.update(r.id, REGIONS, name="Budi S", region="Jawa Barat", chat_id=5)
    assert (r.name, r.region, r.chat_id) == ("Budi S", "Jawa Barat", 5)
    assert store.update(r.id, REGIONS, chat_id=None).chat_id is None
    with pytest.raises(RecipientError):
        store.update(r.id, REGIONS, name=" ")


def test_add_validates_input(store):
    with pytest.raises(RecipientError, match="Nama"):
        store.add("  ", "manager", "Sumatera", REGIONS)
    with pytest.raises(RecipientError, match="Peran"):
        store.add("Budi", "boss", None, REGIONS)
    with pytest.raises(RecipientError, match="Region tidak dikenal"):
        store.add("Budi", "manager", "Papua", REGIONS)


def test_head_never_keeps_a_region(store):
    head = store.add("Bu Rina", "head", "Sumatera", REGIONS)
    assert head.region is None
    assert head.as_dict()["role_label"] == "Atasan (overall)"


def test_invite_codes_are_unique(store):
    a = store.add("A", "manager", "Sumatera", REGIONS)
    b = store.add("B", "manager", "Sumatera", REGIONS)
    assert a.invite_code != b.invite_code


def test_register_links_chat_and_unknown_code_fails(store):
    r = store.add("Budi", "manager", "Sumatera", REGIONS)
    linked = store.register(r.invite_code, 12345)
    assert linked.chat_id == 12345 and linked.connected
    with pytest.raises(KeyError):
        store.register("wrong-code", 1)


def test_send_log_shows_latest_result(store):
    r = store.add("Budi", "manager", "Sumatera", REGIONS, chat_id=1)
    assert store.get(r.id).last_sent_at is None
    store.log_send(r.id, False, "Forbidden")
    store.log_send(r.id, True)
    latest = store.get(r.id)
    assert latest.last_send_ok is True and latest.last_error is None
    assert latest.last_sent_at


def test_delete_removes_recipient_and_its_log(store):
    r = store.add("Budi", "manager", "Sumatera", REGIONS)
    store.log_send(r.id, True)
    store.delete(r.id)
    with pytest.raises(KeyError):
        store.get(r.id)
    with pytest.raises(KeyError):
        store.delete(r.id)
