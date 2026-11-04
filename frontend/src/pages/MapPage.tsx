import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { useRunCtx } from "./RunLayout";
import Inspector, { MobileSheet } from "../components/Inspector";
import { SEV, send } from "../lib/api";
import { Sev } from "../components/ui";

const STYLE = "https://tiles.openfreemap.org/styles/dark"; // OpenFreeMap: free, no key (OSM data)

function haversine(a: number[], b: number[]) {
  const R = 6371008, r = Math.PI / 180;
  const dLat = (b[1] - a[1]) * r, dLon = (b[0] - a[0]) * r;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

export default function MapPage() {
  const { runId, sites, defects, route, media, sel, setSel, reload } = useRunCtx();
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [drawing, setDrawing] = useState<number[][] | null>(null);
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);

  const routeLines = useMemo(() => Object.values(route || {}).map((r: any) => (r.points || []).map((p: any) => [p.lon, p.lat])).filter((l: any) => l.length > 1), [route]);
  const needsRoute = media.length > 0 && routeLines.length === 0 && sites.length === 0;

  // condition-coloured segments (~20 m) along the driven route
  const segments = useMemo(() => {
    const feats: any[] = [];
    const located = defects.filter((d) => d.lat != null && !d.dismissed);
    for (const line of routeLines) {
      let acc: number[][] = [line[0]], dist = 0;
      for (let i = 1; i < line.length; i++) {
        const step = haversine(line[i - 1], line[i]);
        const n = Math.max(1, Math.ceil(step / 20));
        for (let k = 1; k <= n; k++) {
          const p = [line[i - 1][0] + ((line[i][0] - line[i - 1][0]) * k) / n, line[i - 1][1] + ((line[i][1] - line[i - 1][1]) * k) / n];
          acc.push(p); dist += step / n;
          if (dist >= 20) {
            const mid = acc[Math.floor(acc.length / 2)];
            const worst = Math.max(0, ...located.filter((d) => haversine([d.lon!, d.lat!], mid) < 18).map((d) => d.severity));
            feats.push({ type: "Feature", properties: { c: worst ? SEV[worst] : "#5b5b63" }, geometry: { type: "LineString", coordinates: acc } });
            acc = [p]; dist = 0;
          }
        }
      }
      if (acc.length > 1) feats.push({ type: "Feature", properties: { c: "#5b5b63" }, geometry: { type: "LineString", coordinates: acc } });
    }
    return { type: "FeatureCollection", features: feats };
  }, [routeLines, defects]);

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = new maplibregl.Map({ container: el.current, style: STYLE, center: [7.49, 9.06], zoom: 13, attributionControl: { compact: true } });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => setReady(true));
    map.current = m;
    return () => { m.remove(); map.current = null; setReady(false); };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      const src = m.getSource("route") as maplibregl.GeoJSONSource | undefined;
      if (src) src.setData(segments as any);
      else {
        m.addSource("route", { type: "geojson", data: segments as any });
        m.addLayer({ id: "route-glow", type: "line", source: "route", paint: { "line-color": ["get", "c"], "line-width": 12, "line-opacity": 0.25, "line-blur": 6 } });
        m.addLayer({ id: "route", type: "line", source: "route", layout: { "line-cap": "round" }, paint: { "line-color": ["get", "c"], "line-width": 4 } });
      }
      markers.current.forEach((mk) => mk.remove());
      markers.current = sites.map((s) => {
        const worst = Math.max(1, ...s.defect_ids.map((i) => defects.find((d) => d.id === i)?.severity ?? 1));
        const size = 14 + (s.priority_score / 100) * 26;
        const div = document.createElement("div");
        div.className = `relative flex items-center justify-center num text-[10px] text-black ${s.rank <= 10 ? "marker-pulse" : ""}`;
        div.style.cssText = `width:${size}px;height:${size}px;background:${SEV[worst]};border-radius:9999px;color:${SEV[worst]};border:2px solid #0f0e12;cursor:pointer`;
        div.innerHTML = `<span style="color:#000">${s.rank}</span>`;
        div.onclick = () => setSel({ kind: "site", id: s.id });
        return new maplibregl.Marker({ element: div }).setLngLat([s.lon, s.lat]).addTo(m);
      });
      const pts = [...routeLines.flat(), ...sites.map((s) => [s.lon, s.lat])];
      if (pts.length) {
        const b = pts.reduce((bb, p) => bb.extend(p as [number, number]), new maplibregl.LngLatBounds(pts[0] as [number, number], pts[0] as [number, number]));
        m.fitBounds(b, { padding: 80, maxZoom: 17, duration: 600 });
      }
    };
    if (ready) apply();
  }, [segments, sites, defects, ready]);

  // route drawing
  useEffect(() => {
    const m = map.current;
    if (!m || !drawing) return;
    const onClick = (e: maplibregl.MapMouseEvent) => setDrawing((d) => [...(d || []), [e.lngLat.lng, e.lngLat.lat]]);
    m.on("click", onClick);
    m.getCanvas().style.cursor = "crosshair";
    const data: any = { type: "Feature", geometry: { type: "LineString", coordinates: drawing } };
    const src = m.getSource("draw") as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData(data);
    else if (ready) { m.addSource("draw", { type: "geojson", data }); m.addLayer({ id: "draw", type: "line", source: "draw", paint: { "line-color": "#f0a800", "line-width": 3, "line-dasharray": [2, 1] } }); }
    return () => { m.off("click", onClick); m.getCanvas().style.cursor = ""; };
  }, [drawing]);

  async function saveRoute() {
    if (!drawing || drawing.length < 2) return;
    setSaving(true);
    await send(`/api/runs/${runId}/route`, "POST", { media_id: media[0].media_id, points: drawing.map(([lon, lat]) => ({ lat, lon })) });
    setDrawing(null);
    setTimeout(() => { reload(); setSaving(false); }, 4000);
  }

  return (
    <div className="lg:h-full flex flex-col lg:grid lg:grid-cols-[1fr_380px]">
      <MobileSheet />
      <div className="relative bg-carbon h-[62vh] lg:h-auto">
        <div ref={el} style={{ position: "absolute", inset: 0 }} />
        <div className="absolute left-2 top-2 lg:left-4 lg:top-4 bg-mist/95 border hair p-3 w-52 lg:w-64 space-y-2">
          <div className="label">Road condition</div>
          <div className="flex gap-1">{[1, 2, 3, 4, 5].map((n) => <div key={n} className="flex-1 h-2" style={{ background: SEV[n] }} />)}</div>
          <div className="flex justify-between text-[10px] text-muted"><span>minor</span><span>severe</span></div>
                    {(needsRoute || drawing) && (
            <div className="pt-2 border-t hair space-y-2">
              <div className="text-[12px]">{drawing ? `${drawing.length} points. Click along the road you drove, start → end.` : "This footage has no GPS. Draw the route you drove."}</div>
              {!drawing ? <button className="btn btn-solid w-full" onClick={() => setDrawing([])}>Draw route</button> : (
                <div className="flex gap-2"><button className="btn btn-solid flex-1" disabled={drawing.length < 2 || saving} onClick={saveRoute}>{saving ? "Locating…" : "Use route"}</button><button className="btn" onClick={() => setDrawing(null)}>Cancel</button></div>
              )}
            </div>
          )}
          {!needsRoute && !drawing && <button className="text-link text-[11px]" onClick={() => setDrawing([])}>Redraw route</button>}
        </div>
      </div>
      <aside className="lg:border-l hair min-h-0 flex flex-col">
        {sel ? <div className="hidden lg:block h-full"><Inspector /></div> : null}
        {(!sel || true) && (<div className={sel ? "lg:hidden" : ""}>
          <div className="overflow-y-auto">
            <div className="px-4 h-10 flex items-center label border-b hair">Sites by priority</div>
            {sites.map((s) => (
              <button key={s.id} onClick={() => { setSel({ kind: "site", id: s.id }); map.current?.flyTo({ center: [s.lon, s.lat], zoom: 18 }); }} className="w-full text-left px-4 py-3 border-b hair hover:bg-white flex items-center gap-3">
                <span className="num text-[19px] h-light w-8">#{s.rank}</span>
                <div className="flex-1 min-w-0">
                  <div className="truncate">{s.street || "Unnamed road"} <span className="text-muted num">{s.id}</span></div>
                  <div className="text-[11px] text-muted truncate">{s.defect_ids.length} defects{s.pois[0] ? ` · ${s.pois[0].name} ${s.pois[0].distance_m} m` : ""}</div>
                </div>
                <Sev n={Math.max(1, ...s.defect_ids.map((i) => defects.find((d) => d.id === i)?.severity ?? 1))} />
                <span className="num w-10 text-right">{s.priority_score}</span>
              </button>
            ))}
          </div>
        </div>)}
      </aside>
    </div>
  );
}
