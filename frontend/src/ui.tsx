import type { ReactNode } from "react";

export function Panel({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {note && <p>{note}</p>}
      </header>
      {children}
    </section>
  );
}

export function TelegramBubble({ text }: { text: string }) {
  const time = new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  return (
    <div className="tg-chat">
      <div className="tg-bubble">
        <span className="tg-sender">Bot Penjualan</span>
        <p>{text}</p>
        <span className="tg-time">{time}</span>
      </div>
    </div>
  );
}

export function ThemeSwitch({ dark, onToggle }: { dark: boolean; onToggle: () => void }) {
  return (
    <button type="button" role="switch" aria-checked={dark} className="theme-switch" onClick={onToggle}>
      <span className="track" aria-hidden="true">
        <span className="knob" />
      </span>
      Mode gelap
    </button>
  );
}
