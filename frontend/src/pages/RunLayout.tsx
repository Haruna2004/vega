import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { useState } from "react";
import { Logo } from "../components/ui";
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
    <div className="min-h-full lg:h-full flex flex-col">
      <header className="shrink-0 flex flex-wrap lg:flex-nowrap items-center gap-x-5 px-4 border-b hair bg-mist lg:h-12">
        <Logo />
        <div className="text-muted hidden sm:block">/</div>
        <div className="truncate max-w-[180px] sm:max-w-[320px] h-12 lg:h-auto flex items-center">{run.meta?.name ?? runId}</div>
        {run.meta?.status === "running" && <span className="text-[11px] uppercase tracking-widest text-amber">● processing</span>}
        {run.meta?.status === "failed" && <span className="text-[11px] uppercase tracking-widest text-sev5">failed</span>}
        <nav className="order-last lg:order-none w-full lg:w-auto flex h-11 lg:h-full lg:ml-4 overflow-x-auto -mx-4 px-1 lg:mx-0 lg:px-0 border-t hair lg:border-t-0">
          {TABS.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => `h-full shrink-0 flex items-center px-3 border-b-2 ${isActive ? "border-black" : "border-transparent text-muted hover:text-black"}`}>
              {label}
              {to === "defects" && <span className="num ml-1.5 text-[11px] text-muted">{live.length}</span>}
              {to === "orders" && <span className="num ml-1.5 text-[11px] text-muted">{run.sites.length}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-5 text-[12px]">
          {s && <span className="num hidden xl:inline">{s.defects} defects · {s.area_m2} m² · {fmtMoney(s.total_cost, s.symbol)}</span>}
          <a className="btn" href="/app"><span className="hidden sm:inline">All surveys</span><span className="sm:hidden">Surveys</span></a>
        </div>
      </header>
      <main className="flex-1 lg:min-h-0 lg:overflow-hidden">
        <Outlet context={{ ...run, runId, sel, setSel } satisfies RunCtx} />
      </main>
    </div>
  );
}
