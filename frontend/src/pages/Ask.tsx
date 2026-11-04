import { useState } from "react";
import { ArrowUp, Wrench } from "lucide-react";
import { useRunCtx } from "./RunLayout";
import { fileUrl, fmtMoney, send } from "../lib/api";

type Msg = { role: "user" | "assistant"; content: string; steps?: any[] };
const SUGGEST = ["What would it cost to fix everything within 200 m of a school?", "Which 5 sites should we fix first, and why?", "Show me the worst pothole.", "How many defects are in the wheel path?"];

export default function Ask() {
  const { runId, setSel, boq } = useRunCtx();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  async function ask(question: string) {
    if (!question.trim()) return;
    const history = msgs.map(({ role, content }) => ({ role, content }));
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setQ(""); setBusy(true);
    try {
      const r = await send(`/api/runs/${runId}/ask`, "POST", { question, history });
      setMsgs((m) => [...m, { role: "assistant", content: r.answer, steps: r.steps }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "assistant", content: `Error: ${e.message}` }]);
    }
    setBusy(false);
  }
  const linkify = (text: string) => text.split(/(\b[DS]\d{2,3}\b)/g).map((p, i) => /^[DS]\d{2,3}$/.test(p) ? <button key={i} className="num text-link" onClick={() => setSel({ kind: p[0] === "D" ? "defect" : "site", id: p })}>{p}</button> : p);

  return (
    <div className="h-full flex flex-col max-w-[920px] mx-auto w-full">
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {msgs.length === 0 && (
          <div className="pt-10">
            <div className="text-[40px] h-light leading-[1.1]">Ask the roads.</div>
                        <div className="mt-6 grid grid-cols-2 gap-px bg-line border hair">{SUGGEST.map((s) => <button key={s} onClick={() => ask(s)} className="bg-mist hover:bg-white text-left p-3">{s}</button>)}</div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            {m.role === "user" ? <div className="bg-black text-mist px-3 py-2 max-w-[70%]">{m.content}</div> : (
              <div className="space-y-3">
                {(m.steps || []).map((s, j) => <ToolResult key={j} step={s} runId={runId} sym={boq?.symbol} onPick={setSel} />)}
                <div className="text-[14px] leading-relaxed whitespace-pre-wrap">{linkify(m.content)}</div>
              </div>
            )}
          </div>
        ))}
        {busy && <div className="text-muted">Thinking with tools…</div>}
      </div>
      <form className="border-t hair p-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input className="flex-1 py-2.5" placeholder="Ask about defects, sites, costs…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn btn-solid px-3" disabled={busy}><ArrowUp size={14} /></button>
      </form>
    </div>
  );
}

function ToolResult({ step, runId, sym, onPick }: { step: any; runId: string; sym?: string; onPick: (s: any) => void }) {
  const r = step.result;
  const head = <div className="flex items-center gap-1.5 label"><Wrench size={11} /> {step.tool}({Object.entries(step.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})</div>;
  if (step.tool === "show_frame" && r?.image) return <div className="border hair">{head}<img src={fileUrl(runId, r.image)} className="w-full bg-carbon" /></div>;
  if (step.tool === "sum_cost" && r) return (
    <div className="border hair p-3">{head}
      <div className="flex gap-6 mt-2 num"><div><div className="label">works</div>{fmtMoney(r.works, sym)}</div><div><div className="label">mobilisation</div>{fmtMoney(r.mobilisation, sym)}</div><div><div className="label">contingency</div>{fmtMoney(r.contingency, sym)}</div><div><div className="label">total</div><b>{fmtMoney(r.total, sym)}</b></div></div>
      <div className="text-[11px] text-muted mt-1">{r.defects?.join(", ")}</div>
    </div>
  );
  if (Array.isArray(r) && r.length) {
    const cols = Object.keys(r[0]).filter((k) => typeof r[0][k] !== "object").slice(0, 7);
    return (
      <div className="border hair overflow-x-auto">{head}
        <table className="w-full text-[12px]"><thead><tr className="border-b hair">{cols.map((c) => <th key={c} className="text-left font-normal label px-2 py-1">{c}</th>)}</tr></thead>
          <tbody>{r.slice(0, 12).map((row: any, i: number) => <tr key={i} className="border-b hair hover:bg-white cursor-pointer" onClick={() => row.id && onPick({ kind: String(row.id).startsWith("S") ? "site" : "defect", id: row.id })}>{cols.map((c) => <td key={c} className="px-2 py-1 num">{String(row[c] ?? "")}</td>)}</tr>)}</tbody></table>
      </div>
    );
  }
  return <div className="border hair p-2">{head}<pre className="text-[11px] num whitespace-pre-wrap max-h-40 overflow-auto">{JSON.stringify(r, null, 1)}</pre></div>;
}
