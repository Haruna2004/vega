import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Smartphone, Upload } from "lucide-react";
import { Logo, SimBadge } from "../components/ui";
import { fmtMoney, get } from "../lib/api";
import { startRun } from "../lib/upload";

export default function Surveys() {
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
  const [prog, setProg] = useState(0);
  useEffect(() => { get("/api/runs").then(setRuns).catch(() => {}); get("/api/health").then(setHealth).catch(() => {}); get("/api/config").then(setCfg).catch(() => {}); }, []);

  async function start() {
    setBusy(true); setErr("");
    try {
      const id = await startRun(files.map((x) => ({ blob: x, name: x.name })), { name: name || files[0]?.name.replace(/\.[^.]+$/, "") || "Road survey", calibration: { preset, ...(height ? { height_m: +height } : {}) }, currency, max_seconds: maxSec ? +maxSec : null }, setProg);
      nav(`/app/runs/${id}/review`);
    }
    catch (e: any) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="min-h-full">
      <header className="h-12 flex items-center gap-4 px-4 sm:px-6 border-b hair">
        <Logo />
        <nav className="hidden sm:flex gap-4 ml-6"><span className="border-b-2 border-black py-3">Surveys</span><Link to="/" className="text-muted hover:text-black py-3">About</Link></nav>
                <SimBadge provider={health?.provider} />
        <Link to="/capture" className="ml-auto btn flex items-center gap-1.5"><Smartphone size={12} /> Capture on phone</Link>
      </header>
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8 grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-8">
        <section>
          <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
            <div className="text-[26px] h-light">Surveys</div>
            <div className="flex gap-8">
              <div><div className="label">Surveys</div><div className="num text-[19px]">{runs.length}</div></div>
              <div><div className="label">Defects</div><div className="num text-[19px]">{runs.reduce((a, r) => a + (r.summary?.defects ?? 0), 0)}</div></div>
              <div><div className="label">Repair estimate</div><div className="num text-[19px]">{fmtMoney(runs.reduce((a, r) => a + (r.summary?.total_cost ?? 0), 0))}</div></div>
            </div>
          </div>
          
          <div className="border-t hair">
            {runs.length === 0 && <div className="py-6 text-muted">No surveys yet.</div>}
            {runs.map((r) => (
              <Link key={r.id} to={`/app/runs/${r.id}/review`} className="flex items-center gap-4 py-3 border-b hair hover:bg-white px-2">
                <span className="w-2 h-2" style={{ background: r.status === "done" ? "#0f0e12" : r.status === "running" ? "#f0a800" : "#f43f5e" }} />
                <span className="flex-1 truncate">{r.name}</span>
                <span className="num text-muted text-[12px] hidden sm:inline">{new Date(r.created_at * 1000).toLocaleDateString()}</span>
                <span className="num w-20 sm:w-24 text-right hidden sm:inline">{r.summary?.defects ?? "-"} defects</span>
                <span className="num w-24 sm:w-28 text-right">{fmtMoney(r.summary?.total_cost, r.summary?.symbol)}</span>
              </Link>
            ))}
          </div>
        </section>
        <section className="border hair bg-white order-first lg:order-none">
          <div className="px-5 h-11 flex items-center border-b hair label">New survey</div>
          <div className="p-5 space-y-4">
            <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); setFiles([...files, ...Array.from(e.dataTransfer.files)]); }}
              className={`block border border-dashed ${drag ? "border-black bg-mist" : "border-graphite"} p-6 text-center cursor-pointer`}>
              <Upload size={18} className="mx-auto mb-2" />
              <div>Drop road video or photos</div>
                            <input type="file" multiple className="hidden" accept="video/*,image/*,.gpx,.csv" onChange={(e) => setFiles([...files, ...Array.from(e.target.files || [])])} />
            </label>
            {files.length > 0 && <div className="text-[12px] space-y-0.5">{files.map((f, i) => <div key={i} className="flex justify-between"><span className="truncate">{f.name}</span><span className="num text-muted">{(f.size / 1e6).toFixed(1)} MB</span></div>)}</div>}
            <label className="block"><div className="label mb-1">Name</div><input className="w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Zaria Road, Kano" /></label>
            <label className="block"><div className="label mb-1">Camera</div>
              <select className="w-full" value={preset} onChange={(e) => setPreset(e.target.value)}>{cfg && Object.entries(cfg.camera_presets).map(([k, v]: any) => <option key={k} value={k}>{v.label}, {v.height_m} m, {v.hfov_deg}°</option>)}</select>
            </label>
            <div className="grid grid-cols-3 gap-2">
              <label><div className="label mb-1">Height (m)</div><input className="w-full num" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="preset" /></label>
              <label><div className="label mb-1">Currency</div><input className="w-full" value={currency} onChange={(e) => setCurrency(e.target.value)} /></label>
              <label><div className="label mb-1">Max seconds</div><input className="w-full num" value={maxSec} onChange={(e) => setMaxSec(e.target.value)} /></label>
            </div>
            {err && <div className="text-sev5 text-[12px]">{err}</div>}
            <button className="btn btn-solid w-full py-2.5" disabled={!files.length || busy} onClick={start}>{busy ? `Uploading… ${Math.round(prog * 100)}%` : "Start survey"}</button>
                      </div>
        </section>
      </div>
    </div>
  );
}
