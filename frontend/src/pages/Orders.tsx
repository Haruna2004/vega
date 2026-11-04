import { useEffect, useMemo, useRef, useState } from "react";
import { useRunCtx } from "./RunLayout";
import { API, fileUrl, fmtMoney, get, send } from "../lib/api";

export default function Orders() {
  const { runId, docs, boq, sites, reload } = useRunCtx();
  const [active, setActive] = useState("tender");
  const [rates, setRates] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [stamp, setStamp] = useState(0);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => { get(`/api/runs/${runId}/rates`).then(setRates); }, [runId]);
  const doc = docs.find((d) => d.id === active) ?? docs[0];

  // live total from edited rates (same formula as the backend: qty × rate)
  const liveTotal = useMemo(() => {
    if (!boq || !rates) return boq?.total;
    const fx = +rates.fx_from_usd || 1;
    let sub = 0;
    for (const ln of boq.lines) sub += ln.qty * (+(rates.treatments[ln.treatment]?.rate ?? 0) * fx);
    const sitesWith = Object.values(boq.sites).filter((s) => s.lines.length).length;
    sub += sitesWith * (+rates.mobilisation_per_site || 0) * fx;
    return sub * (1 + (+rates.contingency_pct || 0) / 100);
  }, [boq, rates]);

  function edit(path: (r: any) => void) {
    const next = structuredClone(rates);
    path(next);
    setRates(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      setSaving(true);
      await send(`/api/runs/${runId}/rates?pdf=0`, "PUT", next);
      await reload();
      setStamp(Date.now());
      setSaving(false);
    }, 700);
  }
  async function pdf() {
    setSaving(true);
    await send(`/api/runs/${runId}/rates?pdf=1`, "PUT", rates);
    await reload();
    setSaving(false);
    const d = (await get<any[]>(`/api/runs/${runId}/data/documents`)).find((x) => x.id === doc?.id);
    if (d?.pdf) window.open(fileUrl(runId, d.pdf) + `?v=${Date.now()}`, "_blank");
    else window.open(fileUrl(runId, doc!.html), "_blank");
  }
  const used = useMemo(() => new Set(boq?.lines.map((l) => l.treatment)), [boq]);

  return (
    <div className="lg:h-full flex flex-col lg:grid lg:grid-cols-[300px_1fr_340px]">
      <aside className="lg:border-r hair overflow-y-auto max-h-[40vh] lg:max-h-none">
        <div className="px-4 h-10 flex items-center label border-b hair">Documents</div>
        {docs.map((d) => {
          const s = sites.find((x) => x.id === d.site_id);
          return (
            <button key={d.id} onClick={() => setActive(d.id)} className={`w-full text-left px-4 py-3 border-b hair flex items-center gap-3 ${doc?.id === d.id ? "bg-white" : "hover:bg-white"}`}>
              <span className="num w-8 text-muted">{d.kind === "tender" ? "RFQ" : `#${d.rank}`}</span>
              <div className="flex-1 min-w-0"><div className="truncate">{d.kind === "tender" ? "Tender / RFQ (all sites)" : `Work order ${d.id}`}</div><div className="text-[11px] text-muted truncate">{s?.street ?? (d.kind === "tender" ? `${sites.length} sites` : "")}</div></div>
              <span className="num">{fmtMoney(d.total, boq?.symbol)}</span>
            </button>
          );
        })}
      </aside>
      <section className="flex flex-col min-h-0 bg-line h-[75vh] lg:h-auto border-t lg:border-t-0 hair">
        <div className="min-h-10 py-1.5 bg-mist border-b hair flex flex-wrap items-center gap-2 px-4">
          <span className="label">{doc?.kind === "tender" ? "Request for quotation" : "Work order"}</span>
          {saving && <span className="text-[11px] text-amber">updating…</span>}
          <div className="ml-auto flex gap-2">
            <button className="btn btn-solid" onClick={pdf} disabled={!doc}>Download PDF</button>
            {doc && <a className="btn" href={fileUrl(runId, doc.md)} download>Markdown</a>}
            {doc && <a className="btn" href={fileUrl(runId, doc.html)} target="_blank">Print view</a>}
          </div>
        </div>
        {doc && <iframe key={doc.id + stamp} src={fileUrl(runId, doc.html) + `?v=${stamp}`} className="flex-1 w-full bg-white" />}
      </section>
      <aside className="lg:border-l hair overflow-y-auto border-t lg:border-t-0">
        <div className="p-4 border-b hair">
          <div className="label">Estimated total</div>
          <div className="num text-[40px] h-light leading-none mt-1">{fmtMoney(liveTotal, rates?.currency_symbol ?? boq?.symbol)}</div>
          <div className="text-[11px] text-muted mt-1">incl. {rates?.contingency_pct ?? 0}% contingency · placeholder rates</div>
        </div>
        {rates && (
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <label className="col-span-1"><div className="label">Currency</div><input className="w-full" value={rates.currency} onChange={(e) => edit((r) => (r.currency = e.target.value))} /></label>
              <label><div className="label">Symbol</div><input className="w-full" value={rates.currency_symbol} onChange={(e) => edit((r) => (r.currency_symbol = e.target.value))} /></label>
              <label><div className="label">× per USD</div><input className="w-full num" type="number" value={rates.fx_from_usd} onChange={(e) => edit((r) => (r.fx_from_usd = +e.target.value))} /></label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label><div className="label">Contingency %</div><input className="w-full num" type="number" value={rates.contingency_pct} onChange={(e) => edit((r) => (r.contingency_pct = +e.target.value))} /></label>
              <label><div className="label">Mobilisation / site</div><input className="w-full num" type="number" value={rates.mobilisation_per_site} onChange={(e) => edit((r) => (r.mobilisation_per_site = +e.target.value))} /></label>
            </div>
            <div className="label pt-2">Unit rates (USD)</div>
            {Object.entries(rates.treatments as Record<string, any>).filter(([k]) => used.has(k)).map(([k, t]) => (
              <label key={k} className="flex items-center gap-2">
                <span className="flex-1 text-[12px] leading-tight">{t.label}</span>
                <input className="w-20 num text-right" type="number" value={t.rate} onChange={(e) => edit((r) => (r.treatments[k].rate = +e.target.value))} />
                <span className="text-[11px] text-muted w-8">/{t.unit === "m2" ? "m²" : t.unit}</span>
              </label>
            ))}
            <button className="text-link text-[11px]" onClick={async () => { await send(`/api/runs/${runId}/rates`, "DELETE"); setRates(await get(`/api/runs/${runId}/rates`)); await reload(); setStamp(Date.now()); }}>Reset to defaults</button>
          </div>
        )}
      </aside>
    </div>
  );
}
