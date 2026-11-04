"""Stage 3, SAM 3.1 segmentation and tracking.

One Responses API call per (video chunk, concept prompt). SAM returns per-frame
boxes + masks with object ids that are stable inside the call, i.e. tracks.
We stream snapshots into the live view as they arrive, then:
  1. stitch tracks across chunk boundaries (chunks overlap by a few frames),
  2. merge tracks of different prompts that cover the same pixels (IoU > 0.6),
     keeping the more specific label,
  3. drop short / low-confidence tracks.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..config import concept as concept_cfg
from ..config import get_settings
from ..masks import decode, mask_iou, polygons, stored_mask
from ..meta_client import BudgetExceeded, OfflineCacheMiss
from ..store import Run
from . import client

MERGE_IOU = 0.6
STITCH_IOU = 0.45
MAX_FRAME_FRACTION = 0.35  # a "pothole" covering a third of the frame is the road, not a pothole


class SurfaceMatch(RuntimeError):
    """The prompt is segmenting the road itself, not a defect: stop paying for it."""


class JobCollector:
    """Turns cumulative parser snapshots into per-object detections + live events."""

    def __init__(self, run: Run, job: dict, media: dict):
        self.run = run
        self.job = job
        self.media = media
        self.offset = job["start"]
        self.seen = 0
        self.objects: dict[str, dict[int, dict]] = defaultdict(dict)
        self.pending: list[dict] = []
        self.last_flush = time.time()
        self.lock = threading.Lock()
        self.frame_area = media["width"] * media["height"]
        self.big = 0
        self.total = 0
        c = concept_cfg(job["concept"])
        self.color = c["color"]
        self.label = c["label"]

    def on_snapshot(self, snap: Any) -> None:
        records = snap.records
        new = records[self.seen :]
        self.seen = len(records)
        for rec in new:
            if getattr(rec, "kind", None) != "mask":
                continue
            local_frame = rec.frame.frame_index if getattr(rec, "frame", None) is not None else 0
            frame = self.offset + local_frame
            b = rec.bounds
            box = [int(b.left), int(b.top), int(b.right), int(b.bottom)]
            m = stored_mask(rec)
            # cheap pre-check from the box: a box over half the frame is the road, skip the costly decode
            if (box[2] - box[0]) * (box[3] - box[1]) > 0.5 * self.frame_area and self.job["concept"] not in ("standing_water", "rutting", "alligator_crack"):
                self.total += 1
                self.big += 1
                if self.big >= 12 and self.big > 0.6 * self.total:
                    raise SurfaceMatch(f"{self.job['prompt']!r} matched the road surface; stopped early")
                continue
            try:
                arr = decode(m)
            except Exception as exc:  # invalid payload: skip record, keep stream
                self.run.log(f"mask decode failed in {self.job['id']}: {exc}", level="warn")
                continue
            area = int(arr.sum())
            if area == 0:
                continue
            self.total += 1
            if area > MAX_FRAME_FRACTION * self.frame_area:
                self.big += 1
                if self.big >= 12 and self.big > 0.6 * self.total and self.job["concept"] not in ("standing_water", "rutting", "alligator_crack"):
                    raise SurfaceMatch(f"{self.job['prompt']!r} matched the road surface; stopped early")
            rings = polygons(arr, box[0], box[1])
            det = {"f": frame, "b": box, "c": None if rec.confidence is None else round(float(rec.confidence), 3), "a": area, "poly": rings, "m": m}
            self.objects[rec.object_id][frame] = det
            self.pending.append({"o": rec.object_id, "f": frame, "poly": rings, "b": box, "c": det["c"]})
        if self.pending and (len(self.pending) >= 40 or time.time() - self.last_flush > 0.35):
            self.flush()

    def flush(self) -> None:
        if not self.pending:
            return
        self.run.emit("sam_dets", job=self.job["id"], media_id=self.job["media_id"], concept=self.job["concept"], color=self.color, label=self.label, dets=self.pending)
        self.pending = []
        self.last_flush = time.time()


def build_jobs(media: list[dict], plan: list[dict]) -> list[dict]:
    by_media = {m["media_id"]: m for m in media}
    jobs = []
    for p in plan:
        m = by_media[p["media_id"]]
        chunk = next(c for c in m["chunks"] if c["idx"] == p["chunk"])
        for cid in p["concepts"]:
            jobs.append(
                {
                    "id": f"{m['media_id']}_c{chunk['idx']:02d}_{cid}",
                    "media_id": m["media_id"],
                    "kind": "image" if m["kind"] == "photo" else "video",
                    "chunk": chunk["idx"],
                    "start": chunk["start"],
                    "end": chunk["end"],
                    "path": chunk["path"],
                    "concept": cid,
                    "prompt": concept_cfg(cid)["sam_prompt"],
                }
            )
    # interleave so the live view fills the timeline front to back
    jobs.sort(key=lambda j: (j["media_id"], j["chunk"], -concept_cfg(j["concept"]).get("specificity", 0)))
    return jobs


def _stitch(raw: list[dict], media: dict) -> list[dict]:
    """Union tracks of the same concept across overlapping consecutive chunks."""
    parent = list(range(len(raw)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_key: dict[tuple, list[int]] = defaultdict(list)
    for i, t in enumerate(raw):
        by_key[(t["concept"], t["chunk"])].append(i)
    chunks = {c["idx"]: c for c in media["chunks"]}
    for (concept, k), idxs in by_key.items():
        nxt = by_key.get((concept, k + 1), [])
        if not nxt or k + 1 not in chunks:
            continue
        ov = range(chunks[k + 1]["start"], chunks[k]["end"])
        for i in idxs:
            for j in nxt:
                ious = [mask_iou(raw[i]["frames"][f], raw[j]["frames"][f]) for f in ov if f in raw[i]["frames"] and f in raw[j]["frames"]]
                if ious and sum(ious) / len(ious) >= STITCH_IOU:
                    parent[find(j)] = find(i)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(raw)):
        groups[find(i)].append(i)
    out = []
    for members in groups.values():
        members.sort(key=lambda i: raw[i]["chunk"])
        frames: dict[int, dict] = {}
        for i in members:
            for f, d in raw[i]["frames"].items():
                frames.setdefault(f, d)
        first = raw[members[0]]
        out.append({"media_id": first["media_id"], "concept": first["concept"], "prompt": first["prompt"], "sources": [raw[i]["source"] for i in members], "frames": frames})
    return out


def _dedupe(tracks: list[dict]) -> list[dict]:
    """Merge tracks of different concepts that segment the same object."""
    tracks = sorted(tracks, key=lambda t: -concept_cfg(t["concept"]).get("specificity", 0))
    alive = [True] * len(tracks)
    for i, a in enumerate(tracks):
        if not alive[i]:
            continue
        for j in range(i + 1, len(tracks)):
            b = tracks[j]
            if not alive[j] or a["media_id"] != b["media_id"] or a["concept"] == b["concept"]:
                continue
            common = sorted(set(a["frames"]) & set(b["frames"]))
            if not common or len(common) < 0.3 * min(len(a["frames"]), len(b["frames"])):
                continue
            sample = common[:: max(1, len(common) // 10)][:10]
            ious = [mask_iou(a["frames"][f], b["frames"][f]) for f in sample]
            if sum(ious) / len(ious) > MERGE_IOU:
                for f, d in b["frames"].items():
                    a["frames"].setdefault(f, d)
                a.setdefault("merged_from", []).append({"concept": b["concept"], "sources": b["sources"], "iou": round(sum(ious) / len(ious), 3)})
                alive[j] = False
    return [t for t, ok in zip(tracks, alive) if ok]


def finalize_tracks(run: Run, media: list[dict], raw: list[dict]) -> tuple[list[dict], list[dict]]:
    s = get_settings()
    by_media: dict[str, list[dict]] = defaultdict(list)
    for t in raw:
        by_media[t["media_id"]].append(t)
    final: list[dict] = []
    dropped: list[dict] = []
    for m in media:
        stitched = _stitch(by_media.get(m["media_id"], []), m)
        merged = _dedupe(stitched)
        frame_area = m["width"] * m["height"]
        for t in merged:
            dets = [t["frames"][f] for f in sorted(t["frames"])]
            confs = [d["c"] for d in dets if d["c"] is not None]
            mean_conf = sum(confs) / len(confs) if confs else None
            big = sum(1 for d in dets if d["a"] > MAX_FRAME_FRACTION * frame_area)
            reason = None
            if m["kind"] == "video" and len(dets) < s.sam_min_track_frames:
                reason = f"short track ({len(dets)} frames)"
            elif mean_conf is not None and mean_conf < s.sam_min_confidence:
                reason = f"low confidence ({mean_conf:.2f})"
            elif big > len(dets) / 2 and t["concept"] not in ("standing_water", "rutting", "alligator_crack"):
                reason = "mask covers most of the road (prompt matched the surface, not a defect)"
            entry = {
                "media_id": t["media_id"],
                "concept": t["concept"],
                "prompt": t["prompt"],
                "sources": t["sources"],
                "merged_from": t.get("merged_from", []),
                "first": dets[0]["f"],
                "last": dets[-1]["f"],
                "n": len(dets),
                "conf": None if mean_conf is None else round(mean_conf, 3),
                "dets": dets,
            }
            if reason:
                dropped.append({**{k: v for k, v in entry.items() if k != "dets"}, "reason": reason})
            else:
                final.append(entry)
    final.sort(key=lambda t: (t["media_id"], t["first"]))
    for i, t in enumerate(final, 1):
        t["id"] = f"T{i:03d}"
        c = concept_cfg(t["concept"])
        t["label"] = c["label"]
        t["color"] = c["color"]
    return final, dropped


def segment(run: Run) -> dict:
    run.set_stage("segment", "running")
    media = run.read("media")
    plan = run.read("triage")["plan"]
    by_media = {m["media_id"]: m for m in media}
    jobs = build_jobs(media, plan)
    run.log(f"SAM 3.1: {len(jobs)} segmentation calls ({len({j['prompt'] for j in jobs})} prompts)")
    run.emit("sam_plan", jobs=[{k: j[k] for k in ("id", "media_id", "chunk", "start", "end", "concept", "prompt")} for j in jobs])
    raw: list[dict] = []
    job_log: list[dict] = []
    lock = threading.Lock()
    done = 0

    def work(job: dict) -> dict:
        col = JobCollector(run, job, by_media[job["media_id"]])
        run.emit("sam_job", job=job["id"], status="running", media_id=job["media_id"], chunk=job["chunk"], start=job["start"], end=job["end"], concept=job["concept"], prompt=job["prompt"], color=col.color)
        t0 = time.time()
        res = client().sam_segment(job["kind"], run.dir / job["path"], job["prompt"], on_snapshot=col.on_snapshot, tag="sam")
        col.flush()
        return {"job": job, "objects": col.objects, "cached": res.cached, "duration_s": round(time.time() - t0, 2), "api_s": round(res.duration_s, 2), "usage": res.usage, "diagnostics": [str(d) for d in getattr(res.result, "diagnostics", ())][:5]}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(work, j): j for j in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                out = fut.result()
            except SurfaceMatch as exc:
                job_log.append({"id": job["id"], "prompt": job["prompt"], "n_objects": 0, "skipped": str(exc)})
                run.emit("sam_job", job=job["id"], status="done", n_objects=0, skipped=True)
                run.log(str(exc), level="warn")
                continue
            except (OfflineCacheMiss, BudgetExceeded) as exc:
                job_log.append({"id": job["id"], "prompt": job["prompt"], "error": str(exc)})
                run.emit("sam_job", job=job["id"], status="failed", error=str(exc)[:300])
                continue
            except Exception as exc:
                job_log.append({"id": job["id"], "prompt": job["prompt"], "error": f"{type(exc).__name__}: {exc}"[:500]})
                run.emit("sam_job", job=job["id"], status="failed", error=str(exc)[:300])
                run.log(f"SAM call {job['id']} failed: {exc}", level="error")
                continue
            with lock:
                for oid, frames in out["objects"].items():
                    raw.append({"media_id": job["media_id"], "chunk": job["chunk"], "concept": job["concept"], "prompt": job["prompt"], "source": f"{job['id']}#{oid}", "frames": frames})
                done += 1
            job_log.append({"id": job["id"], "prompt": job["prompt"], "n_objects": len(out["objects"]), "cached": out["cached"], "duration_s": out["duration_s"], "api_s": out["api_s"], "usage": out["usage"], "diagnostics": out["diagnostics"]})
            run.emit("sam_job", job=job["id"], status="done", n_objects=len(out["objects"]), cached=out["cached"], duration_s=out["duration_s"])
            run.emit("progress", stage="segment", done=done, total=len(jobs))

    tracks, dropped = finalize_tracks(run, media, raw)
    run.write("detections", {"tracks": tracks, "dropped": dropped, "jobs": sorted(job_log, key=lambda j: j["id"])})
    write_overlays(run, media, tracks)
    run.emit("tracks_final", tracks=[{"id": t["id"], "media_id": t["media_id"], "concept": t["concept"], "label": t["label"], "color": t["color"], "first": t["first"], "last": t["last"], "n": t["n"], "conf": t["conf"], "sources": t["sources"]} for t in tracks], dropped=len(dropped))
    failed = sum(1 for j in job_log if j.get("error"))
    run.set_stage("segment", "done" if failed < len(jobs) or not jobs else "failed", calls=len(jobs), failed=failed, tracks=len(tracks), dropped=len(dropped), raw_objects=len(raw))
    return {"tracks": tracks, "dropped": dropped}


def write_overlays(run: Run, media: list[dict], tracks: list[dict], extra: dict[str, dict] | None = None) -> None:
    """Compact per-frame polygons for the UI player (one file per media)."""
    for m in media:
        ts = [t for t in tracks if t["media_id"] == m["media_id"]]
        frames: dict[int, list] = defaultdict(list)
        for t in ts:
            for d in t["dets"]:
                frames[d["f"]].append([t["id"], d["poly"], d["b"], d["c"]])
        info = {t["id"]: {"concept": t["concept"], "label": t["label"], "color": t["color"], "first": t["first"], "last": t["last"], **((extra or {}).get(t["id"], {}))} for t in ts}
        run.write(f"overlays_{m['media_id']}", {"media_id": m["media_id"], "fps": m.get("fps"), "width": m["width"], "height": m["height"], "n_frames": m["n_frames"], "tracks": info, "frames": {str(k): v for k, v in sorted(frames.items())}})
