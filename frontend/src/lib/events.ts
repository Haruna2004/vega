import { useEffect, useReducer, useRef } from "react";
import { API } from "./api";

export type Entry = { key: string; color: string; label: string; poly: number[][]; box: number[]; c: number | null };
export type LiveDefect = { id: string; label: string; color: string; severity: number; area_m2: number | null; length_m: number | null; conf_low: number | null; conf_high: number | null; evidence?: string; t: number; dismissed: boolean; size_bucket?: string; method: string };
export type EvState = {
  connected: boolean; done: boolean; stages: Record<string, { status: string; info?: any }>; progress: Record<string, { done: number; total: number }>;
  log: { t: number; text: string; level?: string }[]; frames: Map<number, Entry[]>; firstSeen: Map<string, number>; defects: LiveDefect[];
  jobs: Record<string, { start: number; end: number; concept: string; status: string; color?: string }>; triage: { t: number; concepts: string[]; notes?: string }[];
  summary?: any; version: number; processing_s?: number; elapsed: number;
};

const init = (): EvState => ({ connected: false, done: false, stages: {}, progress: {}, log: [], frames: new Map(), firstSeen: new Map(), defects: [], jobs: {}, triage: [], version: 0, elapsed: 0 });

function reduce(s: EvState, ev: any): EvState {
  if (ev.type === "__reset") return init();
  if (ev.type === "__open") return { ...s, connected: true };
  const n: EvState = { ...s, version: s.version + 1, elapsed: ev.t ?? s.elapsed };
  const log = (text: string, level?: string) => { n.log = [...s.log.slice(-80), { t: ev.t, text, level }]; };
  switch (ev.type) {
    case "stage":
      n.stages = { ...s.stages, [ev.stage]: { status: ev.status, info: ev } };
      log(`${ev.stage} ${ev.status}${ev.error ? ": " + ev.error : ""}`, ev.status === "failed" ? "error" : undefined);
      break;
    case "progress": n.progress = { ...s.progress, [ev.stage]: { done: ev.done, total: ev.total } }; break;
    case "log": log(ev.message, ev.level); break;
    case "triage_frame": n.triage = [...s.triage, { t: ev.t_media ?? ev.t, concepts: ev.concepts, notes: ev.notes }]; if (ev.concepts?.length) log(`Muse Spark @${(ev.frame / 15).toFixed(0)}s: ${ev.notes ?? ev.concepts.join(", ")}`); break;
    case "sam_plan": n.jobs = Object.fromEntries(ev.jobs.map((j: any) => [j.id, { start: j.start, end: j.end, concept: j.concept, status: "queued" }])); log(`SAM 3.1 plan: ${ev.jobs.length} segmentation calls`); break;
    case "sam_job": n.jobs = { ...s.jobs, [ev.job]: { ...(s.jobs[ev.job] || { start: ev.start, end: ev.end, concept: ev.concept }), status: ev.status, color: ev.color ?? s.jobs[ev.job]?.color } }; if (ev.status === "done") log(`SAM ${ev.job}: ${ev.n_objects} objects tracked`); break;
    case "sam_dets": {
      const frames = s.frames; // mutate in place for speed; version bump triggers redraw
      for (const d of ev.dets) {
        const key = `${ev.job}#${d.o}`;
        if (!s.firstSeen.has(key)) s.firstSeen.set(key, performance.now());
        const arr = frames.get(d.f) ?? [];
        const i = arr.findIndex((e) => e.key === key);
        const e = { key, color: ev.color, label: ev.label, poly: d.poly, box: d.b, c: d.c };
        if (i >= 0) arr[i] = e; else arr.push(e);
        frames.set(d.f, arr);
      }
      break;
    }
    case "defect": n.defects = [ev.defect, ...s.defects.filter((d) => d.id !== ev.defect.id)]; break;
    case "summary": n.summary = ev; break;
    case "run": if (ev.status === "done" || ev.status === "failed") { n.done = true; n.processing_s = ev.processing_s; } log(`run ${ev.status}`); break;
    case "eof": n.done = true; break;
  }
  return n;
}

/** Subscribe to a run's event stream (live tail or timed replay). */
export function useEvents(runId: string, mode: "off" | "live" | "replay", speed = 4, nonce = 0) {
  const [state, dispatch] = useReducer(reduce, undefined, init);
  const esRef = useRef<EventSource | null>(null);
  useEffect(() => {
    dispatch({ type: "__reset" });
    if (mode === "off") return;
    const url = `${API}/api/runs/${runId}/events${mode === "replay" ? `?replay=1&speed=${speed}` : ""}`;
    const es = new EventSource(url);
    esRef.current = es;
    es.onopen = () => dispatch({ type: "__open" });
    es.onmessage = (m) => { try { const ev = JSON.parse(m.data); dispatch(ev); if (ev.type === "eof") es.close(); } catch {} };
    es.onerror = () => { if (es.readyState === EventSource.CLOSED) dispatch({ type: "eof" }); };
    return () => es.close();
  }, [runId, mode, speed, nonce]);
  return state;
}
