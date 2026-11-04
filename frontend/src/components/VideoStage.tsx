import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { Entry } from "../lib/events";

export type StageHandle = { seek: (t: number) => void; play: () => void; pause: () => void; video: () => HTMLVideoElement | null };

type Props = {
  src: string; fps: number; width: number; height: number;
  getFrame: (f: number) => Entry[] | undefined;
  firstSeen?: Map<string, number>;
  version: number;
  onTime?: (t: number) => void;
  onPick?: (key: string) => void;
};

/** Video on a carbon panel with SAM masks drawn on a synced canvas. */
const VideoStage = forwardRef<StageHandle, Props>(function VideoStage({ src, fps, width, height, getFrame, firstSeen, version, onTime, onPick }, ref) {
  const vref = useRef<HTMLVideoElement>(null);
  const cref = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(0);
  const propsRef = useRef({ getFrame, firstSeen, width, height });
  propsRef.current = { getFrame, firstSeen, width, height };

  useImperativeHandle(ref, () => ({
    seek: (t) => { if (vref.current) { vref.current.currentTime = Math.max(0, t); } },
    play: () => vref.current?.play(),
    pause: () => vref.current?.pause(),
    video: () => vref.current,
  }));

  function draw() {
    const v = vref.current, c = cref.current;
    if (!v || !c) return;
    const rect = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(rect.width * dpr) || c.height !== Math.round(rect.height * dpr)) { c.width = Math.round(rect.width * dpr); c.height = Math.round(rect.height * dpr); }
    const ctx = c.getContext("2d")!;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    const { width: W, height: H, getFrame, firstSeen } = propsRef.current;
    // object-fit: contain mapping
    const s = Math.min(c.width / W, c.height / H);
    const ox = (c.width - W * s) / 2, oy = (c.height - H * s) / 2;
    ctx.setTransform(s, 0, 0, s, ox, oy);
    const entries = getFrame(frameRef.current) || [];
    const now = performance.now();
    for (const e of entries) {
      const age = firstSeen?.get(e.key) ? now - firstSeen.get(e.key)! : 1e9;
      const k = Math.min(1, age / 700); // draw-on progress for new detections
      ctx.lineJoin = "round";
      for (const ring of e.poly) {
        if (ring.length < 6) continue;
        ctx.beginPath();
        ctx.moveTo(ring[0], ring[1]);
        for (let i = 2; i < ring.length; i += 2) ctx.lineTo(ring[i], ring[i + 1]);
        ctx.closePath();
        ctx.globalAlpha = 0.32 * k;
        ctx.fillStyle = e.color;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.strokeStyle = e.color;
        ctx.lineWidth = 2.2 / s;
        if (k < 1) {
          let per = 0;
          for (let i = 2; i < ring.length; i += 2) per += Math.hypot(ring[i] - ring[i - 2], ring[i + 1] - ring[i - 1]);
          ctx.setLineDash([per * k, per]);
        }
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (k < 1) { // pulse ring on first sight
        const [x1, y1, x2, y2] = e.box;
        ctx.globalAlpha = 1 - k;
        ctx.strokeStyle = e.color;
        ctx.lineWidth = 2 / s;
        ctx.beginPath();
        ctx.arc((x1 + x2) / 2, (y1 + y2) / 2, (Math.max(x2 - x1, y2 - y1) / 2 + 10) * (1 + k), 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      // label chip (screen-space size)
      const [x1, y1] = e.box;
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const fs = 11 * dpr;
      ctx.font = `${fs}px "JetBrains Mono", monospace`;
      const text = `${e.label.toUpperCase()}${e.c != null ? " " + e.c.toFixed(2) : ""}`;
      const tw = ctx.measureText(text).width;
      const lx = ox + x1 * s, ly = Math.max(fs + 8, oy + y1 * s - 6);
      ctx.fillStyle = "rgba(15,14,18,.86)";
      ctx.fillRect(lx, ly - fs - 6, tw + 14 * dpr, fs + 8);
      ctx.fillStyle = e.color;
      ctx.fillRect(lx, ly - fs - 6, 3 * dpr, fs + 8);
      ctx.fillStyle = "#f6f8f7";
      ctx.fillText(text, lx + 8 * dpr, ly - 5);
      ctx.restore();
    }
  }

  useEffect(() => {
    const v = vref.current;
    if (!v) return;
    let raf = 0, alive = true;
    const tick = () => {
      if (!alive) return;
      frameRef.current = Math.round(v.currentTime * fps);
      onTime?.(v.currentTime);
      draw();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { alive = false; cancelAnimationFrame(raf); };
  }, [fps]);

  useEffect(() => { draw(); }, [version]);

  function pick(ev: React.MouseEvent) {
    if (!onPick || !cref.current) return;
    const r = cref.current.getBoundingClientRect();
    const s = Math.min(r.width / width, r.height / height);
    const x = (ev.clientX - r.left - (r.width - width * s) / 2) / s;
    const y = (ev.clientY - r.top - (r.height - height * s) / 2) / s;
    const hit = (getFrame(frameRef.current) || []).find((e) => x >= e.box[0] && x <= e.box[2] && y >= e.box[1] && y <= e.box[3]);
    if (hit) onPick(hit.key);
  }

  return (
    <div className="relative w-full h-full bg-carbon">
      <video ref={vref} src={src} className="absolute inset-0 w-full h-full object-contain" muted playsInline loop preload="auto" crossOrigin="anonymous" />
      <canvas ref={cref} className="absolute inset-0 w-full h-full" onClick={pick} />
    </div>
  );
});
export default VideoStage;
