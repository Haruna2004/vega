import { useEffect, useRef, useState } from "react";
import { Camera, Circle, Square } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Logo } from "../components/ui";
import { send } from "../lib/api";

type Fix = { t: number; lat: number; lon: number; acc: number };

/** Mobile capture: record road video from the rear camera while logging GPS
 *  every second, or take geotagged photos; then upload as a new survey. */
export default function Capture() {
  const nav = useNavigate();
  const video = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [fixes, setFixes] = useState<Fix[]>([]);
  const [last, setLast] = useState<Fix | null>(null);
  const [clip, setClip] = useState<Blob | null>(null);
  const [photos, setPhotos] = useState<{ blob: Blob; fix: Fix | null }[]>([]);
  const [secs, setSecs] = useState(0);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const t0 = useRef(0);
  const chunks = useRef<Blob[]>([]);
  const watch = useRef<number | null>(null);

  useEffect(() => {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      .then((s) => { setStream(s); if (video.current) video.current.srcObject = s; })
      .catch((e) => setErr(`Camera unavailable: ${e.message}. Use HTTPS and allow camera access.`));
    watch.current = navigator.geolocation?.watchPosition(
      (p) => setLast({ t: 0, lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy }),
      (e) => setErr((x) => x || `GPS unavailable: ${e.message}`), { enableHighAccuracy: true, maximumAge: 1000 });
    return () => { stream?.getTracks().forEach((t) => t.stop()); if (watch.current != null) navigator.geolocation.clearWatch(watch.current); };
  }, []);

  // log one GPS fix per second while recording
  useEffect(() => {
    if (!rec) return;
    const i = setInterval(() => {
      const t = (Date.now() - t0.current) / 1000;
      setSecs(Math.floor(t));
      if (last) setFixes((f) => [...f, { ...last, t }]);
    }, 1000);
    return () => clearInterval(i);
  }, [rec, last]);

  function startRec() {
    if (!stream) return;
    const type = ["video/mp4", "video/webm;codecs=vp9", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
    const mr = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 6_000_000 } : undefined);
    chunks.current = [];
    mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    mr.onstop = () => setClip(new Blob(chunks.current, { type: mr.mimeType }));
    t0.current = Date.now();
    setFixes(last ? [{ ...last, t: 0 }] : []);
    mr.start(1000);
    setRec(mr);
  }
  function stopRec() { rec?.stop(); setRec(null); }
  function photo() {
    const v = video.current;
    if (!v) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    c.toBlob((b) => b && setPhotos((p) => [...p, { blob: b, fix: last }]), "image/jpeg", 0.92);
  }
  async function upload() {
    setBusy(true); setErr("");
    const f = new FormData();
    if (clip) {
      f.append("files", clip, clip.type.includes("mp4") ? "capture.mp4" : "capture.webm");
      if (fixes.length > 1) f.append("files", new Blob(["t,lat,lon\n" + fixes.map((x) => `${x.t.toFixed(1)},${x.lat},${x.lon}`).join("\n")], { type: "text/csv" }), "capture_route.csv");
    }
    photos.forEach((p, i) => f.append("files", p.blob, `photo_${String(i).padStart(3, "0")}.jpg`));
    if (!clip && photos.some((p) => p.fix)) f.append("route", JSON.stringify(photos.map((p) => ({ lat: p.fix?.lat ?? 0, lon: p.fix?.lon ?? 0 }))));
    f.append("name", `Phone capture ${new Date().toLocaleString()}`);
    f.append("calibration", JSON.stringify({ preset: "phone_dashboard" }));
    try { const r = await send("/api/runs", "POST", f); nav(`/runs/${r.id}/review`); }
    catch (e: any) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="h-full flex flex-col bg-carbon text-mist">
      <header className="h-12 flex items-center px-4 border-b border-carbon-2"><Logo dark /><span className="ml-3 text-graphite text-[12px]">Capture</span>
        <span className="ml-auto num text-[11px]">{last ? `GPS ±${Math.round(last.acc)} m` : "GPS …"}</span></header>
      <div className="relative flex-1 min-h-0">
        <video ref={video} autoPlay playsInline muted className="absolute inset-0 w-full h-full object-cover" />
        {rec && <div className="absolute top-3 left-3 bg-sev5 text-black num px-2 py-0.5 text-[12px]">● REC {secs}s · {fixes.length} GPS fixes</div>}
        {err && <div className="absolute bottom-3 inset-x-3 bg-amber text-black p-2 text-[12px]">{err}</div>}
      </div>
      <div className="p-4 space-y-3 border-t border-carbon-2">
        <div className="text-[12px] text-graphite">Mount the phone on the windscreen, landscape, road in the lower half. Drive at normal speed.</div>
        <div className="flex items-center justify-center gap-8">
          <button onClick={photo} disabled={!stream || !!rec} className="w-12 h-12 border border-graphite flex items-center justify-center disabled:opacity-30"><Camera size={18} /></button>
          {!rec ? <button onClick={startRec} disabled={!stream} className="w-16 h-16 bg-sev5 flex items-center justify-center disabled:opacity-30"><Circle size={22} fill="#000" /></button>
            : <button onClick={stopRec} className="w-16 h-16 bg-mist text-black flex items-center justify-center"><Square size={20} /></button>}
          <div className="w-12 text-center num text-[11px] text-graphite">{photos.length} ph</div>
        </div>
        {(clip || photos.length > 0) && !rec && (
          <button onClick={upload} disabled={busy} className="w-full py-3 bg-mist text-black">{busy ? "Uploading…" : `Send survey (${clip ? `${(clip.size / 1e6).toFixed(0)} MB video, ${fixes.length} GPS fixes` : ""}${photos.length ? ` ${photos.length} photos` : ""})`}</button>
        )}
      </div>
    </div>
  );
}
