import { useMemo, useState } from "react";
import { useRunCtx } from "./RunLayout";
import Inspector, { MobileSheet } from "../components/Inspector";
import { API, fileUrl, rangeText, sizeText } from "../lib/api";
import { Sev, Swatch, Tip } from "../components/ui";

type Key = "id" | "severity" | "size" | "site" | "t";

export default function Defects() {
  const { runId, defects, sel, setSel } = useRunCtx();
  const [view, setView] = useState<"table" | "gallery">(typeof window !== "undefined" && window.innerWidth < 1024 ? "gallery" : "table");
  const [sort, setSort] = useState<Key>("severity");
  const [showDismissed, setShowDismissed] = useState(false);
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const list = defects.filter((d) => (showDismissed || !d.dismissed) && (!q || (d.label + d.id + (d.site_id ?? "")).toLowerCase().includes(q.toLowerCase())));
    const val = (d: any) => (sort === "size" ? d.area_m2 ?? d.length_m ?? 0 : sort === "site" ? d.site_id ?? "" : sort === "t" ? d.t : sort === "id" ? d.id : d.severity);
    return list.sort((a, b) => (val(a) < val(b) ? 1 : -1) * (sort === "id" || sort === "site" || sort === "t" ? -1 : 1));
  }, [defects, sort, showDismissed, q]);
  const th = (k: Key, label: string, cls = "") => <th className={`px-3 py-2 font-normal label cursor-pointer ${cls}`} onClick={() => setSort(k)}>{label}{sort === k ? " ↓" : ""}</th>;

  return (
    <div className="lg:h-full flex flex-col lg:grid lg:grid-cols-[1fr_380px]">
      <MobileSheet />
      <div className="min-h-0 flex flex-col">
        <div className="min-h-11 py-2 px-4 flex flex-wrap items-center gap-3 border-b hair">
          <div className="flex border hair">
            {(["table", "gallery"] as const).map((v) => <button key={v} onClick={() => setView(v)} className={`px-3 py-1 ${view === v ? "bg-black text-mist" : ""}`}>{v}</button>)}
          </div>
          <input placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} className="w-40 sm:w-56" />
          <label className="hidden sm:flex items-center gap-1.5 text-muted"><input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} /> show dismissed by review</label>
          <div className="ml-auto flex gap-2">
            <a className="btn" href={`${API}/api/runs/${runId}/export/csv`}>CSV</a>
            <a className="btn" href={`${API}/api/runs/${runId}/export/geojson`}>GeoJSON</a>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          {view === "table" ? (
            <table className="w-full text-left">
              <thead className="sticky top-0 bg-mist border-b hair"><tr>{th("id", "ID")}<th className="label font-normal px-3">Evidence</th><th className="label font-normal px-3">Type</th>{th("severity", "Sev")}{th("size", "Size", "text-right")}<th className="label font-normal px-3">Range</th><th className="label font-normal px-3">Position</th><th className="label font-normal px-3">Tracked</th>{th("site", "Site")}{th("t", "Time")}<th className="label font-normal px-3">Review</th></tr></thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id} onClick={() => setSel({ kind: "defect", id: d.id })} className={`border-b hair cursor-pointer ${sel?.id === d.id ? "bg-white" : "hover:bg-white"} ${d.dismissed ? "opacity-40" : ""}`}>
                    <td className="px-3 num">{d.id}</td>
                    <td className="px-3 py-1.5"><img src={fileUrl(runId, d.evidence)} className="w-16 h-11 object-cover bg-carbon" loading="lazy" /></td>
                    <td className="px-3"><span className="flex items-center gap-2"><Swatch color={d.color} />{d.label}</span></td>
                    <td className="px-3"><Sev n={d.severity} /></td>
                    <td className="px-3 num text-right"><Tip text={d.method_detail}>{sizeText(d)}</Tip></td>
                    <td className="px-3 num text-muted text-[11px]">{rangeText(d)}</td>
                    <td className="px-3">{d.position.replace("_", " ")}</td>
                    <td className="px-3 num">{d.n_frames} fr</td>
                    <td className="px-3 num">{d.site_id ?? "-"}</td>
                    <td className="px-3 num">{d.t.toFixed(1)}s</td>
                    <td className="px-3 text-[11px] text-muted max-w-[260px] truncate">{d.review?.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-px bg-line border-b hair">
              {rows.map((d) => (
                <button key={d.id} onClick={() => setSel({ kind: "defect", id: d.id })} className={`bg-mist text-left ${d.dismissed ? "opacity-40" : ""}`}>
                  <img src={fileUrl(runId, d.evidence)} className="w-full aspect-[4/3] object-cover bg-carbon" loading="lazy" />
                  <div className="p-2 flex items-center gap-2"><Sev n={d.severity} /><span className="num">{d.id}</span><span className="truncate flex-1">{d.label}</span><span className="num text-muted">{sizeText(d)}</span></div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <aside className="hidden lg:block border-l hair min-h-0"><Inspector /></aside>
    </div>
  );
}
