import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Breakdown, Dashboard, fetchDashboard } from "./api";
import { pct, rupiah } from "./format";
import SendTab from "./SendTab";
import { useTheme } from "./theme";
import { Panel, TelegramBubble, ThemeSwitch } from "./ui";

const TABS = ["Region", "Brand", "Outlet terlemah", "Ringkasan", "Kirim ke Telegram", "Kualitas data"] as const;
type Tab = (typeof TABS)[number];

function tabFromHash(): Tab {
  const fromHash = decodeURIComponent(window.location.hash.slice(1));
  return (TABS as readonly string[]).includes(fromHash) ? (fromHash as Tab) : "Region";
}

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [regions, setRegions] = useState<string[]>([]);
  const [tab, setTabState] = useState<Tab>(tabFromHash);
  const setTab = (t: Tab) => {
    setTabState(t);
    window.location.hash = encodeURIComponent(t); // tab survives reload and can be linked
  };
  const [error, setError] = useState<string | null>(null);
  const [theme, toggleTheme] = useTheme();

  const load = useCallback(async (selected: string[]) => {
    try {
      setError(null);
      setData(await fetchDashboard(selected));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    load(regions);
  }, [regions, load]);


  if (!data) {
    return <main className="page">{error ? <p className="error">{error}</p> : <p className="muted">Memuat data…</p>}</main>;
  }

  const { months, kpi } = data;
  const up = (kpi.change_pct ?? 0) >= 0;
  // `regions` is the filter sent to the API; [] means every region.
  // The pills show what is included, so with no filter every pill is lit.
  const allRegions = data.regions;
  const showsAll = regions.length === 0;
  const isIncluded = (r: string) => showsAll || regions.includes(r);
  const toggleRegion = (r: string) =>
    setRegions((cur) => {
      if (cur.length === 0) return [r]; // from "all", a click focuses on that region
      const next = cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r];
      // Nothing left, or every region picked by hand: back to the plain "all" state.
      return next.length === 0 || next.length === allRegions.length ? [] : next;
    });

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            {/* Official logo, loaded from duakelinci.com rather than copied into this repo.
                If it cannot load (offline), the wordmark alone remains. */}
            <img
              className="brand-logo"
              src="https://www.duakelinci.com/assets/icon/logo-default.svg"
              alt=""
              width={66}
              height={42}
              onError={(e) => (e.currentTarget.style.display = "none")}
            />
            <span className="brand-mark">Dua Kelinci</span>
            <span className="brand-sep" aria-hidden="true" />
            <span className="brand-app">Penjualan</span>
          </div>
          <div className="actions">
            <span className="source">Data: {data.source}</span>
            <ThemeSwitch dark={theme === "dark"} onToggle={toggleTheme} />
          </div>
        </div>
      </header>

      <section className="band">
        <div className="band-inner">
          <p className="band-period">
            {months.latest_label} <span>dibanding {months.previous_label}</span>
          </p>
          <div className="headline">
            <div>
              <span className="headline-label">
                Penjualan bersih · {showsAll ? "semua region" : regions.join(", ")}
              </span>
              <strong className="headline-value">{rupiah(kpi.net_latest)}</strong>
            </div>
            <span className={`delta ${up ? "is-up" : "is-down"}`}>{pct(kpi.change_pct)}</span>
          </div>
          <dl className="facts">
            <div><dt>{months.previous_label}</dt><dd>{rupiah(kpi.net_previous)}</dd></div>
            <div><dt>Outlet aktif</dt><dd>{kpi.active_outlets}</dd></div>
            <div><dt>Invoice</dt><dd>{kpi.invoices.toLocaleString("id-ID")}</dd></div>
          </dl>
          <div className="region-filter" role="group" aria-label="Filter region">
            <button className={`pill on-green ${showsAll ? "active" : ""}`} aria-pressed={showsAll} onClick={() => setRegions([])}>
              Semua region
            </button>
            <span className="filter-sep" aria-hidden="true" />
            {allRegions.map((r) => (
              <button
                key={r}
                className={`pill on-green ${isIncluded(r) ? "active" : ""}`}
                aria-pressed={isIncluded(r)}
                onClick={() => toggleRegion(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
        <svg className="band-edge" viewBox="0 0 1200 24" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 0h1200v10c-40 6-70-4-110 3s-60 9-100 2-70-6-115 1-55 8-95 2-80-7-120 0-50 6-90 1-75-6-115 2-60 5-100-1-70-5-110 2-55 6-95 1-60-4-100 1-50 5-50 5V0z" />
        </svg>
      </section>

      <main className="page">
        {error && <p className="error">{error}</p>}

        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab on" : "tab"} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>

        {tab === "Region" && (
          <>
            <Panel title="Penjualan per region" note="Urut dari total dua bulan">
              <MonthBars rows={data.by_region} dim="region" months={months} />
              <BreakdownTable rows={data.by_region} dim="region" months={months} />
            </Panel>
            <Panel title="Region × brand" note="Total dua bulan; warna makin pekat = penjualan makin besar">
              <RegionBrand matrix={data.region_brand} />
            </Panel>
          </>
        )}

        {tab === "Brand" && (
          <Panel title="Penjualan per brand" note="Urut dari total dua bulan">
            <MonthBars rows={data.by_brand} dim="brand" months={months} />
            <BreakdownTable rows={data.by_brand} dim="brand" months={months} />
          </Panel>
        )}

        {tab === "Outlet terlemah" && <Weakest data={data} />}

        {tab === "Ringkasan" && <Summary text={data.summary} />}

        {tab === "Kirim ke Telegram" && <SendTab regions={data.regions} />}

        {tab === "Kualitas data" && (
          <Panel title="Kualitas data" note="Masalah di CSV dan cara penanganannya. Tidak ada baris yang dibuang diam-diam.">
            <ul className="plain-list">{data.data_quality.lines.map((l) => <li key={l}>{l}</li>)}</ul>
            {data.returns.length > 0 && (
              <>
                <h3>Baris retur</h3>
                <div className="scroll">
                  <table>
                    <thead><tr><th>Tanggal</th><th>Invoice</th><th>Outlet</th><th>SKU</th><th className="num">Qty</th><th className="num">Net</th></tr></thead>
                    <tbody>
                      {data.returns.map((r) => (
                        <tr key={r.invoice_no + r.sku}>
                          <td>{r.date}</td><td>{r.invoice_no}</td><td>{r.outlet_name}</td><td>{r.sku}</td>
                          <td className="num">{r.qty_carton}</td><td className="num down">{rupiah(r.net_sales_idr)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Panel>
        )}
      </main>
    </>
  );
}


type Months = Dashboard["months"];

function MonthBars({ rows, dim, months }: { rows: Breakdown[]; dim: "region" | "brand"; months: Months }) {
  const chart = rows.map((r) => ({
    name: r[dim],
    [months.previous_label]: r.net_previous,
    [months.latest_label]: r.net_latest,
  }));
  return (
    <>
      <div className="legend" aria-hidden="true">
        <span><i className="swatch prev" />{months.previous_label}</span>
        <span><i className="swatch last" />{months.latest_label}</span>
      </div>
      <div className="chart" style={{ height: Math.max(240, rows.length * 52) }}>
        <ResponsiveContainer>
          <BarChart data={chart} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }} barGap={2}>
            <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
            <XAxis type="number" tickFormatter={rupiah} tick={{ fill: "var(--chart-axis)" }} tickLine={false} axisLine={false} fontSize={12} />
            <YAxis type="category" dataKey="name" width={150} tick={{ fill: "var(--chart-label)" }} tickLine={false} axisLine={false} fontSize={13} />
            <Tooltip
              formatter={(v) => rupiah(Number(v))}
              cursor={{ fill: "rgba(var(--heat-rgb), 0.08)" }}
              contentStyle={{
                borderRadius: 12, border: "1px solid var(--line)", fontFamily: "inherit",
                background: "var(--surface)", color: "var(--ink)",
              }}
              labelStyle={{ color: "var(--ink)", fontWeight: 700 }}
            />
            <Bar dataKey={months.previous_label} fill="var(--chart-prev)" radius={[0, 6, 6, 0]} isAnimationActive={false} />
            <Bar dataKey={months.latest_label} fill="var(--chart-last)" radius={[0, 6, 6, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

function BreakdownTable({ rows, dim, months }: { rows: Breakdown[]; dim: "region" | "brand"; months: Months }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>{dim === "region" ? "Region" : "Brand"}</th>
            <th className="num">{months.previous_label}</th>
            <th className="num">{months.latest_label}</th>
            <th className="num">Perubahan</th>
            <th className="num">Total</th>
            <th className="num">Porsi</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r[dim]}>
              <td className="strong">{r[dim]}</td>
              <td className="num">{rupiah(r.net_previous)}</td>
              <td className="num">{rupiah(r.net_latest)}</td>
              <td className={`num ${(r.change_pct ?? 0) >= 0 ? "up" : "down"}`}>{pct(r.change_pct)}</td>
              <td className="num">{rupiah(r.total)}</td>
              <td className="num muted">{pct(r.share_pct).replace("+", "")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RegionBrand({ matrix }: { matrix: Dashboard["region_brand"] }) {
  const max = Math.max(...matrix.rows.flatMap((r) => r.values));
  return (
    <div className="scroll">
      <table className="matrix">
        <thead>
          <tr><th>Region</th>{matrix.brands.map((b) => <th key={b} className="num">{b}</th>)}</tr>
        </thead>
        <tbody>
          {matrix.rows.map((row) => (
            <tr key={row.region}>
              <td className="strong">{row.region}</td>
              {row.values.map((v, i) => (
                <td key={matrix.brands[i]} className="num heat" style={{ "--heat": max > 0 ? v / max : 0 } as React.CSSProperties}>
                  {rupiah(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Weakest({ data }: { data: Dashboard }) {
  const { months } = data;
  return (
    <Panel
      title="5 outlet terlemah"
      note={`Skor gabungan: tren ${months.latest_label} vs ${months.previous_label}, dan penjualan dibanding median outlet sejenis. Dihitung dari semua region; outlet baru tidak dinilai.`}
    >
      <ol className="ranked">
        {data.weakest.map((o, i) => (
          <li key={o.outlet_id}>
            <span className="rank">{i + 1}</span>
            <div className="ranked-body">
              <div className="ranked-title">
                <strong>{o.outlet_name}</strong>
                <span className="muted">{o.outlet_type} · {o.branch} · {o.outlet_id}</span>
              </div>
              <p className="reason">{o.reason}</p>
              <p className="muted small">Salesman: {o.salesman}</p>
            </div>
            <div className="ranked-nums">
              <span className="muted small">{rupiah(o.net_previous)} → </span>
              <strong>{rupiah(o.net_latest)}</strong>
              <span className="down">{pct(o.change_pct)}</span>
            </div>
          </li>
        ))}
      </ol>
      {data.new_outlets.length > 0 && (
        <p className="aside">
          Outlet baru bulan ini:{" "}
          {data.new_outlets.map((o) => `${o.outlet_name} (${o.branch}, ${rupiah(o.net_latest)})`).join(", ")}.
        </p>
      )}
      <details>
        <summary>Skor semua outlet</summary>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Outlet</th><th>Tipe</th><th>Cabang</th><th className="num">Tren</th><th className="num">vs median</th><th className="num">Skor</th></tr>
            </thead>
            <tbody>
              {data.scorecard.map((o) => (
                <tr key={o.outlet_id}>
                  <td>{o.outlet_name} <span className="muted small">{o.outlet_id}</span></td>
                  <td>{o.outlet_type}</td>
                  <td>{o.branch}</td>
                  <td className={`num ${(o.change_pct ?? 0) >= 0 ? "up" : "down"}`}>{pct(o.change_pct)}</td>
                  <td className="num">{o.peer_index === null ? "–" : `${Math.round(o.peer_index * 100)}%`}</td>
                  <td className="num">{o.weakness_score === null ? "baru" : o.weakness_score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Panel>
  );
}


function Summary({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <Panel title="Ringkasan untuk sales manager" note={`Seperti yang terlihat di Telegram. Teks polos, ${text.length} dari 4.096 karakter.`}>
      <TelegramBubble text={text} />
      <button className="pill solid" onClick={copy}>{copied ? "Tersalin" : "Salin teks"}</button>
    </Panel>
  );
}
