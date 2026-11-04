"""Stage 1 — ingest: probe media, build a constant-frame-rate proxy, chunk it for
SAM, sample frames for triage, and resolve GPS."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .. import gps
from ..config import get_settings
from ..meta_client import sha256_file
from ..store import Run

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".3gp"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
ROUTE_EXT = {".gpx", ".csv"}


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return json.loads(out)


def video_stream(probe: dict) -> dict:
    for st in probe.get("streams", []):
        if st.get("codec_type") == "video":
            return st
    raise ValueError("no video stream")


def _rate(text: str | None) -> float:
    if not text or text == "0/0":
        return 0.0
    if "/" in text:
        a, b = text.split("/")
        return float(a) / float(b) if float(b) else 0.0
    return float(text)


def count_frames(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return int(out.split(",")[0])


def make_proxy(src: Path, dst: Path, fps: float, max_height: int, start_s: float | None = None, max_seconds: float | None = None) -> None:
    """Upright, constant-frame-rate H.264 proxy. Frame n of the proxy is frame n
    everywhere (SAM, overlays, UI player), which keeps all indices aligned."""
    vf = f"fps={fps},scale=-2:'min({max_height},ih - mod(ih,2))':flags=lanczos,format=yuv420p"
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start_s:
        cmd += ["-ss", f"{start_s:.3f}"]
    cmd += ["-i", str(src)]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:.3f}"]
    cmd += ["-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-g", str(int(fps)), "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)


def cut_chunk(proxy: Path, dst: Path, start: int, end: int, fps: float) -> None:
    """Frame-exact sub-clip [start, end) of the proxy."""
    vf = f"select='between(n\\,{start}\\,{end - 1})',setpts=N/({fps}*TB)"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(proxy), "-vf", vf, "-r", str(fps), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)],
        check=True,
    )


def plan_chunks(n_frames: int, fps: float, chunk_seconds: float, overlap: int) -> list[tuple[int, int]]:
    size = max(int(round(chunk_seconds * fps)), overlap + 2)
    chunks = []
    start = 0
    while start < n_frames:
        end = min(n_frames, start + size)
        # avoid a tiny tail chunk: fold it into the previous one
        if n_frames - end < max(overlap + 2, int(fps)) and end < n_frames:
            end = n_frames
        chunks.append((start, end))
        if end >= n_frames:
            break
        start = end - overlap
    return chunks


def sample_frames(proxy: Path, out_dir: Path, step: int, prefix: str) -> list[int]:
    """Extract every `step`-th frame as JPEG; returns proxy frame indices."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / f"{prefix}_%06d.jpg"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(proxy), "-vf", f"select='not(mod(n\\,{step}))'", "-fps_mode", "vfr", "-q:v", "3", str(pattern)],
        check=True,
    )
    files = sorted(out_dir.glob(f"{prefix}_*.jpg"))
    indices = []
    for k, f in enumerate(files):
        idx = k * step
        target = out_dir / f"{prefix}_f{idx:06d}.jpg"
        f.rename(target)
        indices.append(idx)
    return indices


def normalise_photo(src: Path, dst: Path, max_side: int = 1600) -> tuple[int, int]:
    from PIL import Image, ImageOps

    if src.suffix.lower() in (".heic", ".heif"):
        try:
            import pillow_heif  # type: ignore

            pillow_heif.register_heif_opener()
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("HEIC input needs `pip install pillow-heif`") from exc
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side))
        im.save(dst, "JPEG", quality=92)
        return im.size


def classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in PHOTO_EXT:
        return "photo"
    if ext in ROUTE_EXT:
        return "route"
    return "unknown"


def ingest(run: Run, inputs: list[Path], *, drawn_route: list[dict] | None = None, start_s: float | None = None, max_seconds: float | None = None) -> dict:
    s = get_settings()
    run.set_stage("ingest", "running")
    media: list[dict] = []
    frames: list[dict] = []
    routes: dict[str, Any] = {}
    route_files = [p for p in inputs if classify(p) == "route"]
    media_files = [p for p in inputs if classify(p) in ("video", "photo")]
    if not media_files:
        raise ValueError("no video or photo inputs")
    max_seconds = max_seconds or float(run.meta.get("settings", {}).get("max_seconds") or 0) or None

    route_points: list[dict] = []
    for rf in route_files:
        route_points += gps.read_gpx(rf) if rf.suffix.lower() == ".gpx" else gps.read_csv_route(rf)

    step = max(1, int(round(s.proxy_fps / s.sample_fps)))
    for mi, src in enumerate(media_files):
        kind = classify(src)
        digest = sha256_file(src)
        media_id = f"m{mi}"
        run.log(f"Ingesting {src.name} ({kind})")
        entry: dict[str, Any] = {"media_id": media_id, "kind": kind, "name": src.name, "src": str(src), "sha256": digest}
        if kind == "video":
            probe = ffprobe(src)
            vs = video_stream(probe)
            proxy = run.dir / f"proxy_{media_id}.mp4"
            make_proxy(src, proxy, s.proxy_fps, s.proxy_height, start_s=start_s, max_seconds=max_seconds)
            pprobe = ffprobe(proxy)
            pvs = video_stream(pprobe)
            n = count_frames(proxy)
            start_time = gps.parse_time(((probe.get("format") or {}).get("tags") or {}).get("creation_time"))
            entry.update(
                {
                    "proxy": run.rel(proxy),
                    "fps": s.proxy_fps,
                    "width": int(pvs["width"]),
                    "height": int(pvs["height"]),
                    "n_frames": n,
                    "duration_s": n / s.proxy_fps,
                    "src_fps": _rate(vs.get("avg_frame_rate")),
                    "src_width": vs.get("width"),
                    "src_height": vs.get("height"),
                    "src_duration_s": float((probe.get("format") or {}).get("duration") or 0),
                    "creation_time": start_time.isoformat() if start_time else None,
                    "device": _device(probe),
                    "trim": {"start_s": start_s or 0.0, "max_seconds": max_seconds},
                }
            )
            chunks = []
            for ci, (a, b) in enumerate(plan_chunks(n, s.proxy_fps, s.chunk_seconds, s.chunk_overlap_frames)):
                cpath = run.dir / "chunks" / f"{media_id}_c{ci:02d}.mp4"
                cut_chunk(proxy, cpath, a, b, s.proxy_fps)
                got = count_frames(cpath)
                if got != b - a:
                    run.log(f"chunk {ci}: expected {b - a} frames, got {got}", level="warn")
                    b = a + got
                chunks.append({"idx": ci, "start": a, "end": b, "path": run.rel(cpath), "sha256": sha256_file(cpath)})
            entry["chunks"] = chunks
            idxs = sample_frames(proxy, run.dir / "frames", step, media_id)
            for idx in idxs:
                frames.append({"id": f"{media_id}:{idx}", "media_id": media_id, "frame": idx, "t": idx / s.proxy_fps, "path": f"frames/{media_id}_f{idx:06d}.jpg"})
            # GPS for this video
            loc = gps.video_location(probe)
            if route_points:
                pts = gps.route_points_for_media(route_points, entry["duration_s"] + (start_s or 0), start_time)
                if start_s:
                    pts = [{**p, "t": p["t"] - start_s} for p in pts]
                routes[media_id] = {"source": "gpx" if route_files[0].suffix.lower() == ".gpx" else "csv", "points": pts}
            elif drawn_route:
                routes[media_id] = {"source": "drawn_route", "points": gps.polyline_over_time(drawn_route, entry["duration_s"])}
            elif loc:
                routes[media_id] = {"source": "video_start_point", "points": [{"t": 0.0, "lat": loc[0], "lon": loc[1]}], "needs_route": True}
            else:
                routes[media_id] = {"source": "none", "points": [], "needs_route": True}
        else:
            dst = run.dir / "frames" / f"{media_id}_f000000.jpg"
            w, h = normalise_photo(src, dst)
            entry.update({"proxy": run.rel(dst), "fps": 0, "width": w, "height": h, "n_frames": 1, "duration_s": 0, "chunks": [{"idx": 0, "start": 0, "end": 1, "path": run.rel(dst), "sha256": sha256_file(dst)}]})
            frames.append({"id": f"{media_id}:0", "media_id": media_id, "frame": 0, "t": 0.0, "path": run.rel(dst)})
            loc = gps.exif_gps(src)
            if loc:
                routes[media_id] = {"source": "exif", "points": [{"t": 0.0, "lat": loc[0], "lon": loc[1]}]}
            elif drawn_route:
                routes[media_id] = {"source": "drawn_route", "points": [{"t": 0.0, **drawn_route[min(mi, len(drawn_route) - 1)]}]}
            else:
                routes[media_id] = {"source": "none", "points": [], "needs_route": True}
        media.append(entry)
        run.emit("media", media=entry)

    run.write("media", media)
    run.write("frames", frames)
    run.write("route", routes)
    sources = sorted({r["source"] for r in routes.values()})
    run.update_meta(gps_source="+".join(sources), inputs=[str(p) for p in inputs])
    total_frames = sum(m["n_frames"] for m in media)
    run.set_stage("ingest", "done", media=len(media), frames=total_frames, sampled=len(frames), gps_source="+".join(sources))
    return {"media": media, "frames": frames, "route": routes}


def _device(probe: dict) -> str | None:
    tags: dict[str, Any] = dict((probe.get("format") or {}).get("tags") or {})
    make = tags.get("com.apple.quicktime.make") or tags.get("make")
    model = tags.get("com.apple.quicktime.model") or tags.get("model")
    if make or model:
        return " ".join(x for x in (make, model) if x)
    return None


def copy_inputs(run: Run, files: list[Path]) -> list[Path]:
    out = []
    for f in files:
        dst = run.dir / "inputs" / f.name
        if f.resolve() != dst.resolve():
            shutil.copy2(f, dst)
        out.append(dst)
    return out


def frame_time(media: dict, frame: int) -> float:
    return frame / media["fps"] if media.get("fps") else 0.0


def ceil_div(a: int, b: int) -> int:
    return int(math.ceil(a / b))
