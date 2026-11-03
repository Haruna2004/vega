"""Stage 8 — annotated MP4 per video: SAM masks, outlines, labels, HUD."""

from __future__ import annotations

import subprocess
from collections import defaultdict

import cv2
import numpy as np

from ..masks import draw_label, draw_overlay
from ..store import Run

SEV_COLORS = {1: "#38BDF8", 2: "#2DD4BF", 3: "#FACC15", 4: "#FB923C", 5: "#F43F5E"}


def _hud(img: np.ndarray, frame: int, fps: float, n_active: int, found: int) -> None:
    h, w = img.shape[:2]
    bar = img[0:34, :].copy()
    cv2.rectangle(bar, (0, 0), (w, 34), (12, 12, 16), -1)
    cv2.addWeighted(bar, 0.65, img[0:34, :], 0.35, 0, dst=img[0:34, :])
    cv2.putText(img, "MEND", (12, 23), cv2.FONT_HERSHEY_DUPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, "SAM 3.1 segmentation + tracking", (78, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (170, 180, 195), 1, cv2.LINE_AA)
    t = frame / fps if fps else 0
    txt = f"t {t:5.1f}s   frame {frame:5d}   in view {n_active}   defects so far {found}"
    (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.putText(img, txt, (w - tw - 12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (210, 220, 230), 1, cv2.LINE_AA)


def render_media(run: Run, media: dict, tracks: list[dict], defects_by_track: dict[str, dict]) -> str | None:
    if media["kind"] != "video":
        return None
    per_frame: dict[int, list] = defaultdict(list)
    for t in tracks:
        for d in t["dets"]:
            per_frame[d["f"]].append((t, d))
    first_seen = sorted((t["first"], t["id"]) for t in tracks if not defects_by_track.get(t["id"], {}).get("dismissed"))
    out = run.dir / f"annotated_{media['media_id']}.mp4"
    W, H = media["width"], media["height"]
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(media["fps"]), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )
    cap = cv2.VideoCapture(str(run.dir / media["proxy"]))
    idx = 0
    found = 0
    fs_i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        while fs_i < len(first_seen) and first_seen[fs_i][0] <= idx:
            found += 1
            fs_i += 1
        active = per_frame.get(idx, [])
        for t, d in active:
            dd = defects_by_track.get(t["id"], {})
            if dd.get("dismissed"):
                draw_overlay(img, d["poly"], "#64748B", alpha=0.1, thickness=1, glow=False)
                continue
            draw_overlay(img, d["poly"], t["color"], alpha=0.36, thickness=2)
        for t, d in active:
            dd = defects_by_track.get(t["id"], {})
            if dd.get("dismissed"):
                continue
            size = ""
            if dd.get("area_m2") is not None and dd.get("quantity_key") != "length_m":
                size = f"  {dd['area_m2']:.2f} m2"
            elif dd.get("length_m") is not None:
                size = f"  {dd['length_m']:.1f} m"
            sev = dd.get("severity")
            label = f"{dd.get('id', t['id'])} {t['label'].upper()}{size}" + (f"  S{sev}" if sev else "")
            draw_label(img, label, d["b"][0], d["b"][1] - 6, SEV_COLORS.get(sev, t["color"]) if sev else t["color"], scale=0.48)
        _hud(img, idx, media["fps"], len([a for a in active if not defects_by_track.get(a[0]["id"], {}).get("dismissed")]), found)
        assert proc.stdin is not None
        proc.stdin.write(img.tobytes())
        idx += 1
    cap.release()
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait()
    return run.rel(out)


def render(run: Run) -> dict:
    run.set_stage("render", "running")
    media = run.read("media")
    tracks = run.read("detections")["tracks"]
    defects = run.read("defects", [])
    by_track = {d["track_id"]: d for d in defects}
    outputs = {}
    for m in media:
        ts = [t for t in tracks if t["media_id"] == m["media_id"]]
        path = render_media(run, m, ts, by_track)
        if path:
            outputs[m["media_id"]] = path
            run.emit("annotated", media_id=m["media_id"], path=path)
    run.write("annotated", outputs)
    run.set_stage("render", "done", videos=len(outputs))
    return outputs
