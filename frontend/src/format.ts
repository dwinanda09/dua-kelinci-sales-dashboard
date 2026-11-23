/** Short IDR format used by sales teams: Rp1,73 M / Rp256,8 jt / Rp950 rb / Rp500. */
export function rupiah(value: number): string {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${sign}Rp${(abs / 1e9).toFixed(2).replace(".", ",")} M`;
  if (abs >= 1e6) return `${sign}Rp${(abs / 1e6).toFixed(1).replace(".", ",")} jt`;
  if (abs >= 1e3) return `${sign}Rp${Math.round(abs / 1e3).toLocaleString("id-ID")} rb`;
  return `${sign}Rp${abs.toLocaleString("id-ID")}`;
}

export function pct(value: number | null): string {
  if (value === null) return "–";
  return `${value > 0 ? "+" : ""}${value.toFixed(1).replace(".", ",")}%`;
}
