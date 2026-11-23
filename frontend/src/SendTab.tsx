import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Recipient,
  SendResult,
  TelegramStatus,
  addRecipient,
  deleteRecipient,
  fetchRecipients,
  fetchTelegramStatus,
  previewReport,
  sendReports,
  setChatId,
} from "./api";
import { Panel, TelegramBubble } from "./ui";

/** Telegram chat IDs are integers; group chats are negative. */
function parseChatId(value: string): number | null | "invalid" {
  const v = value.trim();
  if (!v) return null;
  return /^-?\d+$/.test(v) ? Number(v) : "invalid";
}

/** Pick sales managers / heads and send each their own report on Telegram. */
export default function SendTab({ regions }: { regions: string[] }) {
  const [people, setPeople] = useState<Recipient[]>([]);
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [preview, setPreview] = useState<{ name: string; text: string } | null>(null);
  const [result, setResult] = useState<SendResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, list] = await Promise.all([fetchTelegramStatus(), fetchRecipients()]);
      setStatus(s);
      setPeople(list);
      // Drop selections that are no longer ready (deleted, or chat ID cleared).
      setSelected((cur) => new Set([...cur].filter((id) => list.some((p) => p.id === id && p.connected))));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const run = async (action: () => Promise<void>) => {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const ready = people.filter((p) => p.connected);
  const incomplete = people.length - ready.length;
  const toggle = (id: number) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const selectGroup = (filter: (p: Recipient) => boolean) => setSelected(new Set(ready.filter(filter).map((p) => p.id)));

  const send = () =>
    run(async () => {
      setSending(true);
      try {
        setResult(await sendReports([...selected]));
        setSelected(new Set());
        await refresh();
      } finally {
        setSending(false);
      }
    });

  const botOff = status !== null && !status.configured;

  return (
    <>
      <Panel
        title="Kirim laporan ke Telegram"
        note="Sales manager menerima laporan region-nya. Atasan menerima laporan overall. Hanya penerima dengan chat ID yang bisa dipilih."
      >
        {botOff && (
          <p className="aside warn">
            Bot belum aktif. Isi <code>TELEGRAM_BOT_TOKEN</code> di <code>.env</code>, lalu jalankan <code>./setup.sh</code>.
            Daftar penerima tetap bisa diatur sekarang.
          </p>
        )}
        {status && status.recipients_file.skipped.length > 0 && (
          <div className="aside warn">
            Beberapa baris di <code>config/{status.recipients_file.name}</code> dilewati:
            <ul>{status.recipients_file.skipped.map((s) => <li key={s}>{s}</li>)}</ul>
          </div>
        )}
        {error && <p className="error">{error}</p>}

        <div className="toolbar">
          <div className="toolbar-group">
            <button className="pill outline small" onClick={() => selectGroup((p) => p.role === "manager")}>Semua manager</button>
            <button className="pill outline small" onClick={() => selectGroup((p) => p.role === "head")}>Atasan</button>
            <button className="pill outline small" onClick={() => selectGroup(() => true)}>Semua siap</button>
            {selected.size > 0 && <button className="pill ghost small" onClick={() => setSelected(new Set())}>Batal pilih</button>}
          </div>
          <button className="pill solid" disabled={botOff || selected.size === 0 || sending} onClick={send}>
            {sending ? "Mengirim…" : selected.size ? `Kirim ke ${selected.size} orang` : "Pilih penerima"}
          </button>
        </div>
        <p className="muted small">
          {ready.length} siap kirim{incomplete ? ` · ${incomplete} belum lengkap (isi chat ID atau kirim link undangan)` : ""}
        </p>

        <div className="scroll">
          <table className="recipients">
            <thead>
              <tr>
                <th aria-label="Pilih" />
                <th>Penerima</th>
                <th>Area</th>
                <th>Chat ID Telegram</th>
                <th>Terakhir dikirim</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id} className={p.connected ? "" : "is-incomplete"}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Pilih ${p.name}`}
                      disabled={!p.connected}
                      title={p.connected ? "" : "Lengkapi chat ID dulu"}
                      checked={selected.has(p.id)}
                      onChange={() => toggle(p.id)}
                    />
                  </td>
                  <td>
                    <span className="strong">{p.name}</span>
                    <span className="muted small block">{p.role_label}</span>
                  </td>
                  <td>{p.region ?? "Semua region"}</td>
                  <td>
                    <ChatIdCell person={p} onSaved={refresh} onError={setError} />
                  </td>
                  <td>
                    {p.last_sent_at ? (
                      <span className={p.last_send_ok ? "small" : "small down"} title={p.last_error ?? ""}>
                        {new Date(p.last_sent_at).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" })}
                        {p.last_send_ok ? "" : " · gagal"}
                      </span>
                    ) : (
                      <span className="muted small">belum pernah</span>
                    )}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button className="text-btn" onClick={() => run(async () => setPreview({ name: p.name, text: await previewReport(p.id) }))}>
                        Preview
                      </button>
                      <button
                        className="text-btn quiet"
                        onClick={() =>
                          window.confirm(`Hapus ${p.name} dari daftar penerima?`) &&
                          run(async () => {
                            await deleteRecipient(p.id);
                            await refresh();
                          })
                        }
                      >
                        Hapus
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {people.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    Belum ada penerima. Tambahkan di bawah, atau isi <code>config/recipients.csv</code> lalu jalankan <code>./setup.sh</code>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {result && (
          <div className={`aside ${result.failed ? "warn" : "ok"}`}>
            <strong>Terkirim {result.sent}, gagal {result.failed}.</strong>
            {result.failed > 0 && (
              <ul>
                {result.results.filter((r) => !r.ok).map((r) => (
                  <li key={r.recipient_id}>{r.name}: {r.error}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Panel>

      {preview && (
        <Panel title={`Preview untuk ${preview.name}`}>
          <TelegramBubble text={preview.text} />
        </Panel>
      )}

      <Panel title="Tambah penerima" note="Jumlah bebas: satu region boleh punya lebih dari satu manager. Chat ID boleh diisi nanti.">
        <AddForm regions={regions} onAdded={refresh} onError={setError} />
      </Panel>
    </>
  );
}

function ChatIdCell({ person, onSaved, onError }: { person: Recipient; onSaved: () => void; onError: (m: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(person.chat_id?.toString() ?? "");
  const [copied, setCopied] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    const parsed = parseChatId(value);
    if (parsed === "invalid") {
      onError("Chat ID harus angka, misalnya 123456789 (grup: -100123456789).");
      return;
    }
    try {
      await setChatId(person.id, parsed);
      setEditing(false);
      onSaved();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  async function copyInvite() {
    if (!person.invite_link) return;
    await navigator.clipboard.writeText(person.invite_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (editing) {
    return (
      <form className="inline-form" onSubmit={save}>
        <input
          autoFocus
          inputMode="numeric"
          placeholder="mis. 123456789"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label={`Chat ID ${person.name}`}
        />
        <button className="text-btn" type="submit">Simpan</button>
        <button className="text-btn quiet" type="button" onClick={() => setEditing(false)}>Batal</button>
      </form>
    );
  }

  return (
    <div className="chat-cell">
      {person.connected ? (
        <span className="status ok">{person.chat_id}</span>
      ) : (
        <span className="status missing">Belum ada</span>
      )}
      <button className="text-btn" onClick={() => setEditing(true)}>{person.connected ? "Ubah" : "Isi"}</button>
      {!person.connected && person.invite_link && (
        <button className="text-btn" onClick={copyInvite}>{copied ? "Link tersalin" : "Salin link undangan"}</button>
      )}
    </div>
  );
}

function AddForm({ regions, onAdded, onError }: { regions: string[]; onAdded: () => void; onError: (m: string) => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState<"manager" | "head">("manager");
  const [region, setRegion] = useState(regions[0] ?? "");
  const [chatId, setChat] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const parsed = parseChatId(chatId);
    if (parsed === "invalid") {
      onError("Chat ID harus angka, misalnya 123456789 (grup: -100123456789).");
      return;
    }
    try {
      await addRecipient(name, role, role === "manager" ? region : null, parsed);
      setName("");
      setChat("");
      onAdded();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  return (
    <form className="add-form" onSubmit={submit}>
      <label>
        Nama
        <input placeholder="mis. Budi Santoso" value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Peran
        <select value={role} onChange={(e) => setRole(e.target.value as "manager" | "head")}>
          <option value="manager">Sales Manager (1 region)</option>
          <option value="head">Atasan (overall)</option>
        </select>
      </label>
      <label>
        Region
        <select value={region} disabled={role === "head"} onChange={(e) => setRegion(e.target.value)}>
          {regions.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
      </label>
      <label>
        Chat ID
        <input inputMode="numeric" placeholder="opsional, mis. 123456789" value={chatId} onChange={(e) => setChat(e.target.value)} />
      </label>
      <button className="pill solid" type="submit">Tambah</button>
    </form>
  );
}
