import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Smartphone, Upload } from "lucide-react";
import { Logo, SimBadge } from "../components/ui";
import { fmtMoney, get, send } from "../lib/api";

export default function Home() {
  const nav = useNavigate();
  const [runs, setRuns] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [preset, setPreset] = useState("phone_dashboard");
  const [height, setHeight] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [maxSec, setMaxSec] = useState("180");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [drag, setDrag] = useState(false);
  useEffect(() => { get("/api/runs").then(setRuns).catch(() => {}); get("/api/health").then(setHealth).catch(() => {}); get("/api/config").then(setCfg).catch(() => {}); }, []);

  async function start() {
    setBusy(true); setErr("");
    const f = new FormData();
    files.forEach((x) => f.append("files", x));
    f.append("name", name || files[0]?.name.replace(/\.[^.]+$/, "") || "Road survey");
    f.append("calibration", JSON.stringify({ preset, ...(height ? { height_m: +height } : {}) }));
    f.append("currency", currency);
    if (maxSec) f.append("max_seconds", maxSec);
    try { const r = await send("/api/runs", "POST", f); nav(`/runs/${r.id}/review`); }
    catch (e: any) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="min-h-full">
      <header className="h-12 flex items-center gap-4 px-6 border-b hair">
        <Logo />
        <span className="text-muted">AI road defect audit</span>
        <SimBadge provider={health?.provider} />
        <Link to="/capture" className="ml-auto btn flex items-center gap-1.5"><Smartphone size={12} /> Capture on phone</Link>
      </header>
      <div className="max-w-[1200px] mx-auto px-6 py-10 grid grid-cols-[1fr_420px] gap-10">
        <section>
          <div className="text-[40px] h-light leading-[1.1]">Drive a road. Get a costed,<br />evidence-backed repair plan.</div>
          <div className="text-muted mt-3 max-w-[560px] text-[14px] font-light">SAM 3.1 finds and tracks every pothole and crack pixel by pixel. MEND measures each one, maps it, ranks repairs by risk to people, and writes the work orders and tender. Powered by Muse Spark, SAM 3.1 and Muse Voice Transcribe.</div>
          <div className="mt-10 label mb-2">Surveys</div>
          <div className="border-t hair">
            {runs.length === 0 && <div className="py-6 text-muted">No surveys yet.</div>}
            {runs.map((r) => (
              <Link key={r.id} to={`/runs/${r.id}/review`} className="flex items-center gap-4 py-3 border-b hair hover:bg-white px-2">
                <span className="w-2 h-2" style={{ background: r.status === "done" ? "#0f0e12" : r.status === "running" ? "#f0a800" : "#f43f5e" }} />
                <span className="flex-1 truncate">{r.name}</span>
                <span className="num text-muted text-[12px]">{new Date(r.created_at * 1000).toLocaleDateString()}</span>
                <span className="num w-24 text-right">{r.summary?.defects ?? "—"} defects</span>
                <span className="num w-28 text-right">{fmtMoney(r.summary?.total_cost, r.summary?.symbol)}</span>
              </Link>
            ))}
          </div>
        </section>
        <section className="border hair bg-white">
          <div className="px-5 h-11 flex items-center border-b hair label">New survey</div>
          <div className="p-5 space-y-4">
            <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); setFiles([...files, ...Array.from(e.dataTransfer.files)]); }}
              className={`block border border-dashed ${drag ? "border-black bg-mist" : "border-graphite"} p-6 text-center cursor-pointer`}>
              <Upload size={18} className="mx-auto mb-2" />
              <div>Drop road video or photos</div>
              <div className="text-[11px] text-muted mt-1">.mp4 .mov .jpg .heic · optional .gpx / .csv route</div>
              <input type="file" multiple className="hidden" accept="video/*,image/*,.gpx,.csv" onChange={(e) => setFiles([...files, ...Array.from(e.target.files || [])])} />
            </label>
            {files.length > 0 && <div className="text-[12px] space-y-0.5">{files.map((f, i) => <div key={i} className="flex justify-between"><span className="truncate">{f.name}</span><span className="num text-muted">{(f.size / 1e6).toFixed(1)} MB</span></div>)}</div>}
            <label className="block"><div className="label mb-1">Name</div><input className="w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Zaria Road, Kano" /></label>
            <label className="block"><div className="label mb-1">Camera</div>
              <select className="w-full" value={preset} onChange={(e) => setPreset(e.target.value)}>{cfg && Object.entries(cfg.camera_presets).map(([k, v]: any) => <option key={k} value={k}>{v.label} — {v.height_m} m, {v.hfov_deg}°</option>)}</select>
            </label>
            <div className="grid grid-cols-3 gap-2">
              <label><div className="label mb-1">Height (m)</div><input className="w-full num" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="preset" /></label>
              <label><div className="label mb-1">Currency</div><input className="w-full" value={currency} onChange={(e) => setCurrency(e.target.value)} /></label>
              <label><div className="label mb-1">Max seconds</div><input className="w-full num" value={maxSec} onChange={(e) => setMaxSec(e.target.value)} /></label>
            </div>
            {err && <div className="text-sev5 text-[12px]">{err}</div>}
            <button className="btn btn-solid w-full py-2.5" disabled={!files.length || busy} onClick={start}>{busy ? "Uploading…" : "Start survey"}</button>
            <div className="text-[11px] text-muted">No GPS in the footage? You can draw the route on the map afterwards.</div>
          </div>
        </section>
      </div>
    </div>
  );
}
