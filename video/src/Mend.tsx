import { AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";
import scenes from "./scenes.json";
const { fontFamily: INTER } = loadFont("normal", { weights: ["400", "500", "600", "800"], subsets: ["latin"] });
import lines from "../scripts/lines.json";

export const FPS = 30;
const GAP = 0.7; // seconds of breathing room after each voice clip
const C = { mist: "#f6f8f7", ink: "#1b1c1f", carbon: "#0f0e12", amber: "#f0a800", hair: "rgba(15,14,18,0.14)" };
const FONT = `${INTER}, Arial, sans-serif`;

type Zoom = { at: number; dur: number; x: number; y: number; s: number };
type Scene = { id: string; vo: number; clip?: string; clipStart?: number; rate?: number; lower?: string; zooms?: Zoom[]; kind?: string; lead?: number; still?: string; stillAt?: number; clip2?: string; clip2At?: number; clip2Start?: number };

const S = scenes as Scene[];
const lenOf = (s: Scene) => Math.round(((s.lead || 0) + s.vo + GAP) * FPS);
export const totalFrames = () => S.reduce((a, s) => a + lenOf(s), 0);

function chunks(text: string): string[] {
  const parts = text.match(/[^.,!?]+[.,!?]?/g) || [text];
  const out: string[] = [];
  for (const p of parts.map((x) => x.trim()).filter(Boolean)) {
    const w = p.split(" ");
    if (out.length && out[out.length - 1].split(" ").length + w.length <= 7 && !/[.!?]$/.test(out[out.length - 1])) out[out.length - 1] += " " + p;
    else if (w.length > 11) { const h = Math.ceil(w.length / 2); out.push(w.slice(0, h).join(" "), w.slice(h).join(" ")); }
    else out.push(p);
  }
  return out;
}

const Captions = ({ text, vo }: { text: string; vo: number }) => {
  const f = useCurrentFrame();
  const cs = chunks(text);
  const total = cs.reduce((a, c) => a + c.length, 0);
  let t = 0;
  const spans = cs.map((c) => { const a = t; t += (c.length / total) * vo; return { c, a, b: t }; });
  const now = f / FPS;
  const cur = spans.find((s) => now >= s.a && now < s.b);
  if (!cur) return null;
  return (
    <div style={{ position: "absolute", bottom: 64, width: "100%", display: "flex", justifyContent: "center" }}>
      <div style={{ background: "rgba(15,14,18,0.86)", color: "#fff", fontFamily: FONT, fontSize: 38, fontWeight: 500, padding: "12px 24px", letterSpacing: -0.2, maxWidth: 1500, textAlign: "center" }}>{cur.c.replace(/,$/, "")}</div>
    </div>
  );
};

const Lower = ({ label }: { label: string }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - 12, fps, config: { damping: 200 } });
  const out = interpolate(f, [5.5 * fps, 6 * fps], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: 64, top: 64, opacity: p * out, transform: `translateX(${(1 - p) * -30}px)`, display: "flex", alignItems: "stretch", fontFamily: FONT }}>
      <div style={{ width: 6, background: C.amber }} />
      <div style={{ background: C.carbon, color: "#fff", fontSize: 30, fontWeight: 600, padding: "12px 22px", letterSpacing: 0.2 }}>{label}</div>
    </div>
  );
};

function zoomAt(z: Zoom[] | undefined, t: number) {
  let s = 1, x = 0.5, y = 0.5;
  for (const k of z || []) {
    const ease = Easing.inOut(Easing.cubic);
    const inP = interpolate(t, [k.at, k.at + 0.8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
    const outP = interpolate(t, [k.at + k.dur, k.at + k.dur + 0.8], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
    const p = Math.min(inP, outP);
    if (p > 0) { s = 1 + (k.s - 1) * p; x = 0.5 + (k.x - 0.5) * p; y = 0.5 + (k.y - 0.5) * p; }
  }
  return { s, x, y };
}

const Clip = ({ sc }: { sc: Scene }) => {
  const f = useCurrentFrame();
  const { s, x, y } = zoomAt(sc.zooms, f / FPS);
  return (
    <AbsoluteFill style={{ transform: `scale(${s})`, transformOrigin: `${x * 100}% ${y * 100}%` }}>
      {sc.clip2 && f >= (sc.clip2At || 0) * FPS ? (
        <Sequence from={Math.round((sc.clip2At || 0) * FPS)}>
          <OffthreadVideo src={staticFile(sc.clip2)} startFrom={Math.round((sc.clip2Start || 0) * FPS)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        </Sequence>
      ) : (
        <OffthreadVideo src={staticFile(sc.clip!)} startFrom={Math.round((sc.clipStart || 0) * FPS)} playbackRate={sc.rate || 1} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      )}
    </AbsoluteFill>
  );
};

const Still = ({ src, at }: { src: string; at: number }) => {
  const f = useCurrentFrame() - at * FPS;
  if (f < 0) return null;
  const o = interpolate(f, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const y = interpolate(f, [20, 9 * FPS], [0, -520], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  return (
    <AbsoluteFill style={{ background: C.mist, opacity: o, alignItems: "center", overflow: "hidden" }}>
      <Img src={staticFile(src)} style={{ width: 860, marginTop: 60, transform: `translateY(${y}px)`, boxShadow: "0 0 0 1px rgba(15,14,18,0.14)" }} />
    </AbsoluteFill>
  );
};

const Title = () => {
  const f = useCurrentFrame();
  const o = interpolate(f, [10, 30, 4.2 * FPS, 5 * FPS], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: o, background: "rgba(15,14,18,0.45)" }}>
      <div style={{ fontFamily: FONT, color: "#fff", textAlign: "center" }}>
        <div style={{ fontSize: 150, fontWeight: 800, letterSpacing: 18 }}>MEND</div>
        <div style={{ height: 6, width: 120, background: C.amber, margin: "18px auto 26px" }} />
        <div style={{ fontSize: 40, fontWeight: 400, opacity: 0.92 }}>Road repair plans from a single drive</div>
      </div>
    </AbsoluteFill>
  );
};

const EndCard = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: C.mist, justifyContent: "center", alignItems: "center", fontFamily: FONT, color: C.ink }}>
      <div style={{ opacity: p, transform: `translateY(${(1 - p) * 20}px)`, textAlign: "center" }}>
        <div style={{ fontSize: 130, fontWeight: 800, letterSpacing: 16, color: C.carbon }}>MEND</div>
        <div style={{ height: 6, width: 120, background: C.amber, margin: "14px auto 40px" }} />
        <div style={{ fontSize: 46, fontWeight: 600 }}>mend.harunafaruk.com</div>
        <div style={{ fontSize: 32, marginTop: 14, opacity: 0.7 }}>github.com/Haruna2004/vega</div>
        <div style={{ marginTop: 60, display: "flex", gap: 0, justifyContent: "center", border: `1px solid ${C.hair}` }}>
          {["Muse Spark 1.3", "SAM 3.1", "Muse Voice Transcribe"].map((m, i) => (
            <div key={m} style={{ padding: "16px 30px", fontSize: 28, fontWeight: 500, borderLeft: i ? `1px solid ${C.hair}` : "none" }}>{m}</div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const Mend = () => {
  let at = 0;
  return (
    <AbsoluteFill style={{ background: C.carbon }}>
      {S.map((sc) => {
        const from = at;
        const dur = lenOf(sc);
        at += dur;
        const lead = Math.round((sc.lead || 0) * FPS);
        return (
          <Sequence key={sc.id} from={from} durationInFrames={dur}>
            {sc.kind === "end" ? <EndCard /> : <Clip sc={sc} />}
            {sc.still && <Still src={sc.still} at={sc.stillAt || 0} />}
            {sc.kind === "title" && <Title />}
            <Sequence from={lead}>
              <Audio src={staticFile(`vo3/${sc.id}.wav`)} />
              <Captions text={(lines as any)[sc.id]} vo={sc.vo} />
            </Sequence>
            {sc.lower && <Lower label={sc.lower} />}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
