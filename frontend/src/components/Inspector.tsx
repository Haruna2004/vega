import { useState } from "react";
import { X } from "lucide-react";
import { useRunCtx } from "../pages/RunLayout";
import { fileUrl, fmtMoney, rangeText, sizeText } from "../lib/api";
import { DefectLine, Sev, Swatch, Tip } from "./ui";
import VoiceNote from "./VoiceNote";

export default function Inspector({ onSeek }: { onSeek?: (t: number) => void }) {
  const { sel, setSel, defects, sites, runId, boq, reload } = useRunCtx();
  const [raw, setRaw] = useState(false);
  if (!sel) return <div className="p-5 text-muted">Select a defect or site to inspect it.</div>;
  const header = (title: string) => (
    <div className="flex items-center justify-between px-4 h-10 border-b hair">
      <div className="label">{title}</div>
      <button onClick={() => setSel(null)}><X size={14} /></button>
    </div>
  );
  if (sel.kind === "defect") {
    const d = defects.find((x) => x.id === sel.id);
    if (!d) return null;
    const line = boq?.lines.find((l) => l.defect_id === d.id);
    return (
      <div className="h-full overflow-y-auto">
        {header(`Defect ${d.id}`)}
        <div className="bg-carbon">
          <img src={fileUrl(runId, raw ? d.evidence_raw : d.evidence)} className="w-full aspect-[4/3] object-contain" />
        </div>
        <div className="flex border-b hair text-[12px]">
          <button className={`flex-1 py-1.5 ${!raw ? "bg-white" : "text-muted"}`} onClick={() => setRaw(false)}>SAM mask</button>
          <button className={`flex-1 py-1.5 ${raw ? "bg-white" : "text-muted"}`} onClick={() => setRaw(true)}>Raw pixels</button>
        </div>
        <div className="p-4 space-y-4">
          <div className="flex items-center gap-3">
            <Sev n={d.severity} big />
            <div>
              <div className="text-[19px] h-light flex items-center gap-2"><Swatch color={d.color} />{d.label}</div>
              <div className="text-muted">{d.site_id ? <button className="text-link" onClick={() => setSel({ kind: "site", id: d.site_id! })}>Site {d.site_id}</button> : "not located"} · {d.position.replace("_", " ")}</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><div className="label">Size</div><div className="num text-[19px]"><Tip text={d.method_detail}>{sizeText(d)}</Tip></div><div className="text-[11px] text-muted">{rangeText(d)}</div></div>
            <div><div className="label">Tracked</div><div className="num text-[19px]">{d.n_frames} fr</div><div className="text-[11px] text-muted">SAM conf {d.conf ?? "n/a"}</div></div>
            {d.lateral_m != null && <div><div className="label">Offset</div><div className="num">{d.lateral_m > 0 ? "+" : ""}{d.lateral_m} m · {d.distance_m} m ahead</div></div>}
            {line && <div><div className="label">Repair</div><div className="num">{fmtMoney(line.amount, boq?.symbol)}</div><div className="text-[11px] text-muted">{line.qty} {line.unit} {line.description.split("(")[0]}</div></div>}
          </div>
          <div>
            <div className="label mb-1">Why severity {d.severity}</div>
            <ul className="text-[12px] space-y-0.5">{(d.severity_factors || []).map((f) => <li key={f}>· {f}</li>)}</ul>
            {d.severity_spark != null && <div className="text-[12px] mt-1">Muse Spark review: {d.severity_spark}/5 → blended {d.severity}</div>}
          </div>
          {d.review && <div className="border-l-2 border-black pl-3 text-[12px]"><div className="label">Crop review</div>{d.review.notes} <span className="text-muted">(depth {d.review.depth}, edge {d.review.edge_condition})</span></div>}
          <div className="text-[11px] text-muted">Method: {d.method.replace("_", " ")}. {d.method_detail}</div>
          <div className="flex gap-2">
            {onSeek && <button className="btn" onClick={() => onSeek(d.t)}>Show in video</button>}
            <a className="btn" href={fileUrl(runId, d.evidence_frame)} target="_blank">Full frame</a>
          </div>
          {(d.notes || []).map((n) => <div key={n.voice_id} className="text-[12px]">Note: “{n.transcript}”</div>)}
          <VoiceNote runId={runId} kind="defect" id={d.id} onDone={() => reload()} />
        </div>
      </div>
    );
  }
  const s = sites.find((x) => x.id === sel.id);
  if (!s) return null;
  const ds = s.defect_ids.map((i) => defects.find((d) => d.id === i)!).filter(Boolean);
  return (
    <div className="h-full overflow-y-auto">
      {header(`Site ${s.id}`)}
      <div className="p-4 space-y-4">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[26px] h-light">Rank #{s.rank}</div>
            <div className="text-muted">{s.street || "Unnamed road"}{s.area ? `, ${s.area}` : ""} · {s.road_class}</div>
          </div>
          <div className="text-right"><div className="label">Priority</div><div className="num text-[26px] h-light">{s.priority_score}</div></div>
        </div>
        {s.rationale && <div className="border-l-2 border-black pl-3 text-[12px]">{s.rationale}<div className="text-muted mt-1">— {s.rationale_by === "muse-spark" ? "Muse Spark" : "rules"}</div></div>}
        <div>
          <div className="label mb-1">Score factors</div>
          <ul className="text-[12px] space-y-0.5">{s.factors.map((f) => <li key={f}>· {f}</li>)}</ul>
        </div>
        {s.pois.length > 0 && <div><div className="label mb-1">Nearby</div>{s.pois.slice(0, 5).map((p) => <div key={p.name + p.kind} className="text-[12px] flex justify-between"><span>{p.name}</span><span className="num text-muted">{p.kind.replace("_", " ")} · {p.distance_m} m</span></div>)}</div>}
        <div>
          <div className="label mb-1">Defects</div>
          <div className="border-t hair">{ds.map((d) => <DefectLine key={d.id} d={d} onClick={() => setSel({ kind: "defect", id: d.id })} />)}</div>
        </div>
        <div className="flex justify-between"><span className="label">Site total</span><span className="num">{fmtMoney(boq?.sites[s.id]?.total, boq?.symbol)}</span></div>
        {s.voice && <div className="text-[12px]">Field note: “{s.voice.transcript}”</div>}
        <VoiceNote runId={runId} kind="site" id={s.id} onDone={() => reload()} />
      </div>
    </div>
  );
}
