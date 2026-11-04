import { useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { send } from "../lib/api";

export default function VoiceNote({ runId, kind, id, onDone }: { runId: string; kind: "site" | "defect"; id: string; onDone: (r: any) => void }) {
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const chunks = useRef<Blob[]>([]);

  async function submit(form: FormData) {
    setBusy(true); setErr("");
    form.append("target_kind", kind); form.append("target_id", id);
    try { const r = await send(`/api/runs/${runId}/voice`, "POST", form); setResult(r); onDone(r); }
    catch (e: any) { setErr(String(e.message).slice(0, 200)); }
    setBusy(false);
  }
  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(stream);
    chunks.current = [];
    mr.ondataavailable = (e) => chunks.current.push(e.data);
    mr.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks.current, { type: mr.mimeType });
      const f = new FormData(); f.append("audio", blob, mr.mimeType.includes("mp4") ? "note.mp4" : "note.webm");
      submit(f);
    };
    mr.start(); setRec(mr);
  }
  function stop() { rec?.stop(); setRec(null); }

  return (
    <div className="border hair bg-white p-3 space-y-2">
      <div className="label">Field note</div>
      <div className="flex gap-2">
        <button className={`btn flex items-center gap-1.5 ${rec ? "btn-solid" : ""}`} disabled={busy} onPointerDown={start} onPointerUp={stop} onPointerLeave={() => rec && stop()}>
          {rec ? <Square size={12} /> : <Mic size={12} />} {rec ? "Recording… release to send" : "Hold to record"}
        </button>
      </div>
      <div className="flex gap-2">
        <input className="flex-1" placeholder="…or type the note" value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn" disabled={busy || !text} onClick={() => { const f = new FormData(); f.append("text", text); submit(f); }}>Add</button>
      </div>
      {busy && <div className="text-muted">Transcribing and re-ranking…</div>}
      {err && <div className="text-sev5">{err}</div>}
      {result && (
        <div className="text-[12px] space-y-1">
          <div>“{result.note.transcript}”</div>
          <div className="text-muted">{result.note.model} · tags: {(result.note.intent?.tags || []).join(", ") || "none"} · exposure ×{result.note.intent?.exposure_multiplier ?? 1}</div>
          {result.old_rank !== result.new_rank && <div className="num">Rank #{result.old_rank} → <b>#{result.new_rank}</b></div>}
        </div>
      )}
    </div>
  );
}
