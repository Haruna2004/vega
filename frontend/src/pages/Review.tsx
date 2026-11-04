import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Circle, Loader2, Pause, Play, RotateCcw, X } from "lucide-react";
import { useRunCtx } from "./RunLayout";
import VideoStage, { StageHandle } from "../components/VideoStage";
import Inspector, { MobileSheet } from "../components/Inspector";
import { Entry, useEvents } from "../lib/events";
import { Overlays, data, fileUrl, fmtMoney, fmtTime, sizeText } from "../lib/api";
import { Sev, Stat, Swatch } from "../components/ui";

const STAGES: [string, string, string][] = [
  ["ingest", "Ingest", "ffmpeg · frame-exact proxy + chunks"],
  ["triage", "Triage", "Muse Spark · which prompts where"],
  ["segment", "Segment + track", "SAM 3.1 · masks, track ids"],
  ["measure", "Measure", "ground-plane model + Spark crop review"],
  ["geo", "Locate", "GPS route · OSM schools, hospitals"],
  ["prioritize", "Prioritize", "severity × exposure · Spark rationale"],
  ["report", "Work orders", "BoQ · RFQ · PDF"],
  ["render", "Annotated video", "masks burned into MP4"],
];

export default function Review() {
  const ctx = useRunCtx();
  const { runId, media, defects, meta, sel, setSel, boq } = ctx;
  const m = media[0];
  const running = meta?.status === "running";
  const [mode, setMode] = useState<"off" | "live" | "replay">("off");
  const [speed, setSpeed] = useState(4);
  const [nonce, setNonce] = useState(0);
  const ev = useEvents(runId, mode, speed, nonce);
  const [ov, setOv] = useState<Overlays | null>(null);
  const [t, setT] = useState(0);
  const headRef = useRef<HTMLDivElement>(null);
  const fillRef = useRef<HTMLDivElement>(null);
  const lastSec = useRef(-1);
  // playhead moves every frame without re-rendering the page; text updates 4x a second
  const onTime = (time: number) => {
    const d = media[0]?.duration_s || 1;
    const pct = Math.min(100, (time / d) * 100);
    if (headRef.current) headRef.current.style.transform = `translateX(${pct}cqw)`;
    if (fillRef.current) fillRef.current.style.width = `${pct}%`;
    const q = Math.floor(time * 4);
    if (q !== lastSec.current) { lastSec.current = q; setT(time); }
  };
  const [playing, setPlaying] = useState(true);
  const stage = useRef<StageHandle>(null);

  useEffect(() => { if (running) setMode("live"); }, [running]);
  useEffect(() => { if (m && meta?.status === "done") data<Overlays>(runId, `overlays_${m.media_id}`).then(setOv).catch(() => {}); }, [runId, m?.media_id, meta?.status]);
  useEffect(() => { if (ev.done && mode === "live") ctx.reload(); }, [ev.done]);

  const useLive = mode !== "off";
  const trackToDefect = useMemo(() => Object.fromEntries(Object.entries(ov?.tracks || {}).map(([k, v]) => [k, v.defect_id])), [ov]);
  const getFrame = useMemo(() => {
    if (useLive) return (f: number) => ev.frames.get(f);
    const cache = new Map<number, Entry[]>();
    return (f: number) => {
      if (!ov) return undefined;
      if (cache.has(f)) return cache.get(f);
      const rows = ov.frames[String(f)] || [];
      const out = rows.filter(([tid]) => !ov.tracks[tid]?.dismissed).map(([tid, poly, box, c]) => {
        const info = ov.tracks[tid];
        return { key: tid, color: info.color, label: `${info.defect_id ?? tid} ${info.label}${info.area_m2 ? " " + info.area_m2.toFixed(2) + "m²" : ""}`, poly, box, c };
      });
      cache.set(f, out);
      return out;
    };
  }, [useLive, ov, ev.version]);

  // defects shown in the right feed / counters
  const live = useLive ? ev.defects.filter((d) => !d.dismissed) : defects.filter((d) => !d.dismissed);
  const area = live.reduce((a, d: any) => a + (d.area_m2 && d.quantity_key !== "length_m" ? d.area_m2 : 0), 0);
  const cost = useLive ? (ev.summary?.total_cost ?? live.reduce((a, d: any) => a + estCost(d), 0)) : boq?.total;
  const severe = live.filter((d) => d.severity >= 4).length;
  const stageStatus = (k: string) => (useLive ? ev.stages[k]?.status : meta?.stages?.[k]?.status) ?? "pending";

  // keyboard: space play/pause, J/K next/prev defect
  const sorted = useMemo(() => [...defects].filter((d) => !d.dismissed).sort((a, b) => a.t - b.t), [defects]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === " ") { e.preventDefault(); toggle(); }
      if (e.key === "j" || e.key === "k") {
        const next = e.key === "j" ? sorted.find((d) => d.t > t + 0.2) : [...sorted].reverse().find((d) => d.t < t - 0.2);
        if (next) { stage.current?.seek(Math.max(0, next.t - 0.5)); setSel({ kind: "defect", id: next.id }); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  function toggle() { const v = stage.current?.video(); if (!v) return; if (v.paused) { v.play(); setPlaying(true); } else { v.pause(); setPlaying(false); } }

  if (!m) return <div className="p-10 text-muted">{running ? "Ingesting footage…" : "No media in this run."}</div>;
  const dur = m.duration_s || 1;

  return (
    <div className="lg:h-full flex flex-col lg:grid lg:grid-cols-[280px_1fr_380px]">
      {/* pipeline */}
      <aside className="order-3 lg:order-none border-t lg:border-t-0 lg:border-r hair flex flex-col min-h-0">
        <div className="px-4 h-10 flex items-center justify-between border-b hair">
          <span className="label">Pipeline</span>
          {meta?.processing_s && !useLive && <span className="num text-[11px] text-muted">{fmtTime(meta.processing_s)} total</span>}
        </div>
        <div>
          {STAGES.map(([k, label, sub]) => {
            const st = stageStatus(k);
            const p = useLive ? ev.progress[k] : undefined;
            const info = meta?.stages?.[k];
            const dt = info?.finished_at && info?.started_at ? info.finished_at - info.started_at : undefined;
            return (
              <div key={k} className={`px-4 py-2.5 border-b hair ${st === "running" ? "bg-white" : ""}`}>
                <div className="flex items-center gap-2">
                  {st === "done" ? <Check size={13} /> : st === "running" ? <Loader2 size={13} className="animate-spin" /> : st === "failed" ? <X size={13} className="text-sev5" /> : <Circle size={11} className="text-graphite" />}
                  <span className={st === "pending" ? "text-muted" : ""}>{label}</span>
                  {!useLive && dt !== undefined && <span className="num ml-auto text-[11px] text-muted">{dt < 1 ? "<1s" : `${dt.toFixed(0)}s`}</span>}
                  {p && st === "running" && <span className="num ml-auto text-[11px]">{p.done}/{p.total}</span>}
                </div>
                                {p && st === "running" && <div className="ml-5 mt-1 h-[2px] bg-line"><div className="h-full bg-black transition-all" style={{ width: `${(100 * p.done) / Math.max(1, p.total)}%` }} /></div>}
              </div>
            );
          })}
        </div>
        <div className="px-4 h-9 flex items-center border-b hair label">Log</div>
        <div className="flex-1 overflow-y-auto px-4 py-2 num text-[10.5px] leading-relaxed text-muted flex flex-col-reverse">
          <div>{(useLive ? ev.log : []).map((l, i) => <div key={i} className={l.level === "error" ? "text-sev5" : l.level === "warn" ? "text-black" : ""}>{l.t?.toFixed(1).padStart(6)} {l.text}</div>)}</div>
          
        </div>
      </aside>

      {/* video */}
      <section className="order-1 lg:order-none flex flex-col min-h-0 min-w-0">
        <div className="aspect-video lg:aspect-auto lg:flex-1 min-h-0">
          <VideoStage ref={stage} src={fileUrl(runId, m.proxy)} fps={m.fps} width={m.width} height={m.height} getFrame={getFrame} firstSeen={useLive ? ev.firstSeen : undefined} version={useLive ? ev.version : ov ? 1 : 0}
            onTime={onTime} onPick={(key) => { const did = trackToDefect[key]; if (did) setSel({ kind: "defect", id: did }); }} />
        </div>
        {/* timeline */}
        <div className="border-t hair bg-mist px-4 pt-2 pb-3">
          <div className="flex items-center gap-3 mb-2">
            <button onClick={toggle} className="btn px-2 py-1">{playing ? <Pause size={12} /> : <Play size={12} />}</button>
            <span className="num">{fmtTime(t)} / {fmtTime(dur)}</span>
            
            <div className="ml-auto flex items-center gap-2">
              {meta?.status === "done" && (
                <>
                  <select value={speed} onChange={(e) => setSpeed(+e.target.value)} className="py-0.5">{[1, 2, 4, 8, 16].map((s) => <option key={s} value={s}>{s}×</option>)}</select>
                  <button className="btn flex items-center gap-1" onClick={() => { setMode("replay"); setNonce((n) => n + 1); stage.current?.seek(0); }}><RotateCcw size={12} /> Replay processing</button>
                  {useLive && <button className="btn" onClick={() => setMode("off")}>Show final</button>}
                </>
              )}
            </div>
          </div>
          <div className="relative h-14 cursor-pointer" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); stage.current?.seek(((e.clientX - r.left) / r.width) * dur); }}>
            {/* SAM chunk coverage */}
            <div className="absolute inset-x-0 top-0 h-2 bg-line">
              <div ref={fillRef} className="absolute inset-y-0 left-0 bg-graphite/60" />
              {Object.values(ev.jobs).map((j, i) => <div key={i} className="absolute h-full" style={{ left: `${(j.start / m.fps / dur) * 100}%`, width: `${((j.end - j.start) / m.fps / dur) * 100}%`, background: j.status === "done" ? "#0f0e12" : j.status === "running" ? "#f0a800" : "transparent", opacity: 0.5 }} />)}
            </div>
            {/* defect tracks */}
            <div className="absolute inset-x-0 top-3 bottom-0">
              {(useLive ? [] : sorted).map((d, i) => (
                <div key={d.id} title={`${d.id} ${d.label}`} onClick={(e) => { e.stopPropagation(); stage.current?.seek(Math.max(0, d.t - 0.5)); setSel({ kind: "defect", id: d.id }); }}
                  className="absolute h-[6px] hover:h-[9px]" style={{ left: `${(d.first / m.fps / dur) * 100}%`, width: `${Math.max(0.4, ((d.last - d.first) / m.fps / dur) * 100)}%`, top: `${(i % 5) * 8}px`, background: d.color, outline: sel?.id === d.id ? "1px solid #000" : undefined }} />
              ))}
            </div>
            <div className="absolute inset-0 pointer-events-none" style={{ containerType: "inline-size" }}><div ref={headRef} className="absolute top-0 h-[30px] left-0 w-[4px] -ml-[2px] bg-black will-change-transform" /></div>
          </div>
        </div>
      </section>

      {/* counters + feed / inspector */}
      <aside className="order-2 lg:order-none border-t lg:border-t-0 lg:border-l hair flex flex-col min-h-0">
        <MobileSheet onSeek={(tt) => stage.current?.seek(Math.max(0, tt - 0.5))} />
        <div className="grid grid-cols-4 lg:grid-cols-2 gap-3 lg:gap-4 p-4 border-b hair">
          <Stat label="Defects" value={live.length} />
          <Stat label="Damage" value={`${area.toFixed(1)} m²`} />
          <Stat label="Est. cost" value={fmtMoney(cost, boq?.symbol)} />
          <Stat label="Severe" value={severe} />
        </div>
        <div className="flex-1 min-h-0">
          {sel ? <div className="hidden lg:block h-full"><Inspector onSeek={(tt) => stage.current?.seek(Math.max(0, tt - 0.5))} /></div> : (
            <div className="h-full overflow-y-auto">
              <div className="px-4 h-9 flex items-center label border-b hair">{useLive ? "Found so far" : "Defects in this drive"}</div>
              {live.map((d: any) => (
                <button key={d.id} onClick={() => { setSel({ kind: "defect", id: d.id }); stage.current?.seek(Math.max(0, d.t - 0.5)); }} className="w-full flex gap-3 p-3 border-b hair hover:bg-white text-left">
                  {d.evidence ? <img src={fileUrl(runId, d.evidence)} className="w-20 h-14 object-cover bg-carbon" /> : <div className="w-20 h-14 bg-carbon" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2"><Sev n={d.severity} /><span className="num">{d.id}</span><Swatch color={d.color} /><span className="truncate">{d.label}</span></div>
                    <div className="num text-[12px] mt-1">{sizeText(d)}</div>
                    <div className="num text-[11px] text-muted">{fmtTime(d.t)}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function estCost(d: any): number {
  // rough live estimate before the BoQ exists; replaced by the real total at the end
  if (d.area_m2 && d.quantity_key !== "length_m") return d.area_m2 * 1.3 * 45;
  if (d.length_m) return d.length_m * 3.5;
  return 60;
}
