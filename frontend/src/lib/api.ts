export const API = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export type Defect = {
  id: string; track_id: string; media_id: string; site_id?: string; concept: string; label: string; color: string;
  severity: number; severity_rule?: number; severity_spark?: number; severity_factors?: string[];
  area_m2: number | null; width_m: number | null; length_m: number | null; conf_low: number | null; conf_high: number | null;
  quantity_key?: string; size_bucket?: string; method: string; method_detail: string; position: string;
  lateral_m: number | null; distance_m: number | null; best_frame: number; t: number; first: number; last: number;
  n_frames: number; conf: number | null; evidence?: string; evidence_frame?: string; evidence_raw?: string;
  review?: { is_defect: boolean; depth: string; edge_condition: string; severity: number; notes: string };
  dismissed: boolean; lat?: number; lon?: number; partial?: boolean; notes?: { voice_id: string; transcript: string }[];
};
export type Poi = { kind: string; name: string; distance_m: number; lat: number; lon: number };
export type Site = {
  id: string; lat: number; lon: number; media_id: string; t: number; defect_ids: string[]; street?: string | null; area?: string | null;
  road_class?: string; pois: Poi[]; rank: number; priority_score: number; severity_score: number; exposure: number; factors: string[];
  rationale?: string; rationale_by?: string; voice?: { id: string; transcript: string; model: string; intent: any; audio?: string | null };
};
export type Media = { media_id: string; kind: string; name: string; proxy: string; fps: number; width: number; height: number; n_frames: number; duration_s: number; chunks: { idx: number; start: number; end: number }[] };
export type Overlays = { fps: number; width: number; height: number; n_frames: number; tracks: Record<string, { concept: string; label: string; color: string; first: number; last: number; defect_id?: string; severity?: number; area_m2?: number | null; dismissed?: boolean }>; frames: Record<string, [string, number[][], number[], number | null][]> };
export type Summary = { defects: number; sites: number; area_m2: number; crack_m: number; total_cost: number; currency: string; symbol: string; severe: number; pdf: boolean };
export type RunMeta = { id: string; name: string; created_at: number; status: string; provider?: string; stages: Record<string, { status: string; started_at?: number; finished_at?: number; error?: string; [k: string]: any }>; summary?: Summary; processing_s?: number; gps_source?: string; running?: boolean; settings?: any; calibration?: any; currency?: string };
export type BoqLine = { defect_id: string; site_id: string; treatment: string; description: string; unit: string; qty: number; rate: number; amount: number; basis: string; estimated: boolean };
export type Boq = { currency: string; symbol: string; fx_from_usd: number; contingency_pct: number; lines: BoqLine[]; sites: Record<string, { lines: BoqLine[]; works: number; mobilisation: number; total: number }>; by_treatment: any[]; subtotal: number; contingency: number; total: number };
export type Doc = { id: string; kind: string; site_id?: string; rank?: number; total: number; md: string; html: string; pdf?: string };

export async function get<T = any>(path: string): Promise<T> {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
export async function send<T = any>(path: string, method: string, body?: any): Promise<T> {
  const isForm = body instanceof FormData;
  const r = await fetch(API + path, { method, body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined, headers: isForm || body === undefined ? undefined : { "Content-Type": "application/json" } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
export const fileUrl = (runId: string, path?: string | null) => (path ? `${API}/api/runs/${runId}/files/${path}` : "");
export const data = <T = any>(runId: string, name: string) => get<T>(`/api/runs/${runId}/data/${name}`);

export const SEV = ["", "#38bdf8", "#2dd4bf", "#facc15", "#fb923c", "#f43f5e"];
export const fmtMoney = (v: number | undefined, sym = "$") => (v === undefined || v === null ? "-" : `${sym}${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
export function sizeText(d: Defect): string {
  if (d.area_m2 != null && d.quantity_key !== "length_m") return `${d.area_m2.toFixed(2)} m²`;
  if (d.length_m != null) return `${d.length_m.toFixed(1)} m`;
  return d.size_bucket ? `size ${d.size_bucket}` : "-";
}
export function rangeText(d: Defect): string {
  if (d.conf_low == null || d.conf_high == null) return "no metric size";
  const u = d.quantity_key === "length_m" ? "m" : "m²";
  return `${d.conf_low.toFixed(2)}–${d.conf_high.toFixed(2)} ${u}`;
}
export const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
