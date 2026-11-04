import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Defect, SEV } from "../lib/api";

export function Logo({ dark = false, to = "/app" }: { dark?: boolean; to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 select-none">
      <svg width="18" height="18" viewBox="0 0 32 32"><rect width="32" height="32" fill={dark ? "#f6f8f7" : "#0f0e12"} /><path d="M6 24V8l10 10L26 8v16" fill="none" stroke={dark ? "#0f0e12" : "#f6f8f7"} strokeWidth="2.5" /><rect x="22" y="21" width="4" height="4" fill="#f0a800" /></svg>
      <span className="h-light text-[17px] tracking-[0.18em]">MEND</span>
    </Link>
  );
}

export function Sev({ n, big = false }: { n: number; big?: boolean }) {
  return <span className={`num inline-flex items-center justify-center text-black ${big ? "w-8 h-8 text-[15px]" : "w-5 h-5 text-[11px]"}`} style={{ background: SEV[n] }} title={`severity ${n} of 5`}>{n}</span>;
}

export function Swatch({ color }: { color: string }) {
  return <span className="inline-block w-2.5 h-2.5 shrink-0" style={{ background: color }} />;
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="border-l hair pl-3">
      <div className="label">{label}</div>
      <div className="num text-[26px] h-light leading-tight">{value}</div>
      {sub && <div className="text-[11px] text-muted">{sub}</div>}
    </div>
  );
}

export function SimBadge({ provider }: { provider?: string }) {
  if (provider !== "simulate") return null;
  return <span className="text-[10px] tracking-widest uppercase bg-amber text-black px-1.5 py-0.5" title="No Meta API key configured: AI outputs come from engine/mend/simulate.py">Simulated AI</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-10 text-muted">{children}</div>;
}

export function Tip({ text, children }: { text: string; children: ReactNode }) {
  return <span title={text} className="underline decoration-dotted decoration-graphite underline-offset-2 cursor-help">{children}</span>;
}

export function DefectLine({ d, active, onClick }: { d: Defect; active?: boolean; onClick?: () => void }) {
  return (
    <button onClick={onClick} className={`w-full text-left flex items-center gap-2 px-3 py-2 border-b hair ${active ? "bg-white" : "hover:bg-white"} ${d.dismissed ? "opacity-40" : ""}`}>
      <Sev n={d.severity} />
      <span className="num w-10">{d.id}</span>
      <Swatch color={d.color} />
      <span className="flex-1 truncate">{d.label}</span>
      <span className="num text-muted">{d.area_m2 != null && d.quantity_key !== "length_m" ? `${d.area_m2.toFixed(2)} m²` : d.length_m != null ? `${d.length_m.toFixed(1)} m` : d.size_bucket ?? ""}</span>
    </button>
  );
}
