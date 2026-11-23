export interface Breakdown {
  net_previous: number;
  net_latest: number;
  total: number;
  change_pct: number | null;
  share_pct: number;
  region?: string;
  brand?: string;
}

export interface Outlet {
  outlet_id: string;
  outlet_name: string;
  outlet_type: string;
  region: string;
  branch: string;
  salesman: string;
  net_previous: number;
  net_latest: number;
  change_pct: number | null;
  peer_index: number | null;
  weakness_score: number | null;
  days_since_order: number;
  is_new: boolean;
  reason?: string;
}

export interface Dashboard {
  source: string;
  months: { previous: string; latest: string; previous_label: string; latest_label: string };
  regions: string[];
  kpi: {
    net_previous: number;
    net_latest: number;
    change_pct: number | null;
    active_outlets: number;
    invoices: number;
  };
  by_region: Breakdown[];
  by_brand: Breakdown[];
  region_brand: { brands: string[]; rows: { region: string; values: number[] }[] };
  weakest: Outlet[];
  new_outlets: Outlet[];
  scorecard: Outlet[];
  summary: string;
  data_quality: { lines: string[] };
  returns: { date: string; invoice_no: string; outlet_name: string; sku: string; qty_carton: number; net_sales_idr: number }[];
}

async function check(res: Response): Promise<Response> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d: { msg?: string }) => d.msg).join("; ") // FastAPI validation errors
      : body.detail;
    throw new Error(detail ?? `HTTP ${res.status}`);
  }
  return res;
}

export async function fetchDashboard(regions: string[]): Promise<Dashboard> {
  const params = new URLSearchParams();
  regions.forEach((r) => params.append("region", r));
  const res = await check(await fetch(`/api/dashboard?${params}`));
  return res.json();
}



export interface Recipient {
  id: number;
  name: string;
  role: "manager" | "head";
  role_label: string;
  region: string | null;
  chat_id: number | null;
  connected: boolean;
  invite_link: string | null;
  last_sent_at: string | null;
  last_send_ok: boolean | null;
  last_error: string | null;
}

export interface SendResult {
  sent: number;
  failed: number;
  results: { recipient_id: number; name: string; ok: boolean; error: string | null }[];
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface TelegramStatus {
  configured: boolean;
  bot_username: string | null;
  recipients_file: { name: string; added: number; updated: number; skipped: string[] };
}

export async function fetchTelegramStatus(): Promise<TelegramStatus> {
  return (await check(await fetch("/api/telegram"))).json();
}

export async function fetchRecipients(): Promise<Recipient[]> {
  return (await check(await fetch("/api/recipients"))).json();
}

export async function addRecipient(name: string, role: string, region: string | null, chatId: number | null): Promise<void> {
  await check(await fetch("/api/recipients", json({ name, role, region, chat_id: chatId })));
}

export async function setChatId(id: number, chatId: number | null): Promise<void> {
  await check(await fetch(`/api/recipients/${id}`, { ...json({ chat_id: chatId }), method: "PATCH" }));
}

export async function deleteRecipient(id: number): Promise<void> {
  await check(await fetch(`/api/recipients/${id}`, { method: "DELETE" }));
}

export async function previewReport(id: number): Promise<string> {
  return (await (await check(await fetch(`/api/recipients/${id}/preview`))).json()).text;
}

export async function sendReports(ids: number[]): Promise<SendResult> {
  return (await check(await fetch("/api/send", json({ recipient_ids: ids })))).json();
}
