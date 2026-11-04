import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { useState } from "react";
import { Logo, SimBadge } from "../components/ui";
import { useRun, RunData } from "../lib/useRun";
import { fmtMoney } from "../lib/api";

export type Sel = { kind: "defect" | "site"; id: string } | null;
export type RunCtx = RunData & { runId: string; reload: () => Promise<void>; sel: Sel; setSel: (s: Sel) => void };
export const useRunCtx = () => useOutletContext<RunCtx>();

const TABS = [["review", "Review"], ["map", "Map"], ["defects", "Defects"], ["orders", "Work orders"], ["ask", "Ask"]] as const;

export default function RunLayout() {
  const { runId = "" } = useParams();
  const run = useRun(runId);
  const [sel, setSel] = useState<Sel>(null);
  const live = run.defects.filter((d) => !d.dismissed);
  const s = run.meta?.summary;
  return (
    <div className="h-full flex flex-col">
      <header className="h-12 shrink-0 flex items-center gap-5 px-4 border-b hair bg-mist">
        <Logo />
        <div className="text-muted">/</div>
        <div className="truncate max-w-[320px]">{run.meta?.name ?? runId}</div>
        <SimBadge provider={run.meta?.provider} />
        {run.meta?.status === "running" && <span className="text-[11px] uppercase tracking-widest text-amber">● processing</span>}
        {run.meta?.status === "failed" && <span className="text-[11px] uppercase tracking-widest text-sev5">failed</span>}
        <nav className="flex h-full ml-4">
          {TABS.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => `h-full flex items-center px-3 border-b-2 ${isActive ? "border-black" : "border-transparent text-muted hover:text-black"}`}>
              {label}
              {to === "defects" && <span className="num ml-1.5 text-[11px] text-muted">{live.length}</span>}
              {to === "orders" && <span className="num ml-1.5 text-[11px] text-muted">{run.sites.length}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-5 text-[12px]">
          {s && <span className="num">{s.defects} defects · {s.area_m2} m² · {fmtMoney(s.total_cost, s.symbol)}</span>}
          <a className="btn" href="/app">All surveys</a>
        </div>
      </header>
      <main className="flex-1 min-h-0">
        <Outlet context={{ ...run, runId, sel, setSel } satisfies RunCtx} />
      </main>
    </div>
  );
}
