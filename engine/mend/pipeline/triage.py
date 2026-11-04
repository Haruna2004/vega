"""Stage 2 — triage with Muse Spark: which SAM prompts to run on which chunk.

Frames sampled every `MEND_TRIAGE_EVERY_S` are sent in batches (several images per
request) with a strict JSON schema. The union of flagged concepts per chunk, plus
the baseline prompts, becomes that chunk's SAM plan. Chunks where no frame shows a
road are skipped entirely, which is where most of the credit saving comes from.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from ..config import baseline_concepts, concept_ids, get_settings
from ..meta_client import MetaAPIError
from ..prompts import image_part, render, text_part
from ..store import Run
from . import client

BATCH = 6
MAX_CONCEPTS_PER_CHUNK = 6
SURFACES = ["asphalt", "concrete", "gravel", "dirt", "paving_blocks", "other", "unknown"]
WEATHER = ["clear", "overcast", "rain", "wet_road", "fog", "unknown"]
LIGHTING = ["day", "dusk", "night", "glare", "unknown"]


def triage_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "frames": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "index": {"type": "integer"},
                        "road_visible": {"type": "boolean"},
                        "surface_type": {"type": "string", "enum": SURFACES},
                        "weather": {"type": "string", "enum": WEATHER},
                        "lighting": {"type": "string", "enum": LIGHTING},
                        "defect_concepts": {"type": "array", "items": {"type": "string", "enum": concept_ids()}},
                        "notes": {"type": "string"},
                    },
                    "required": ["index", "road_visible", "surface_type", "weather", "lighting", "defect_concepts", "notes"],
                },
            }
        },
        "required": ["frames"],
    }


def pick_triage_frames(frames: list[dict], every_s: float) -> list[dict]:
    picked: list[dict] = []
    last: dict[str, float] = {}
    for f in frames:
        mid = f["media_id"]
        if mid not in last or f["t"] - last[mid] >= every_s - 1e-6:
            picked.append(f)
            last[mid] = f["t"]
    return picked


def _triage_batch(run: Run, batch: list[dict]) -> list[dict]:
    system = render("triage", concepts=concept_ids())
    content: list[dict] = [text_part(f"{len(batch)} frames follow. Frame indices: {', '.join(str(i) for i in range(len(batch)))}.")]
    for i, f in enumerate(batch):
        content.append(text_part(f"Frame index {i} (t={f['t']:.1f}s):"))
        content.append(image_part(run.dir / f["path"], max_side=768))
    out = client().spark_json(
        [{"role": "system", "content": system}, {"role": "user", "content": content}],
        triage_schema(),
        name="triage",
        model=get_settings().spark_fast_model,
        reasoning_effort="low",
        tag="triage",
    )
    results = []
    by_index = {r.get("index"): r for r in out.get("frames", [])}
    for i, f in enumerate(batch):
        r = by_index.get(i) or {"road_visible": True, "defect_concepts": [], "notes": "no triage result", "surface_type": "unknown", "weather": "unknown", "lighting": "unknown"}
        concepts = [c for c in r.get("defect_concepts", []) if c in concept_ids()]
        results.append({"frame_id": f["id"], "media_id": f["media_id"], "frame": f["frame"], "t": f["t"], "path": f["path"], **{k: r.get(k) for k in ("road_visible", "surface_type", "weather", "lighting", "notes")}, "defect_concepts": concepts})
    return results


def plan_for_chunks(media: list[dict], triaged: list[dict], baseline: list[str], *, triage_ok: bool) -> list[dict]:
    plan = []
    for m in media:
        fps = m.get("fps") or 1.0
        for c in m["chunks"]:
            t0, t1 = c["start"] / fps, c["end"] / fps
            inside = [r for r in triaged if r["media_id"] == m["media_id"] and t0 - 1.0 <= r["t"] <= t1 + 1.0]
            if m["kind"] == "photo":
                inside = [r for r in triaged if r["media_id"] == m["media_id"]]
            counts = Counter(cid for r in inside for cid in r["defect_concepts"])
            road_seen = any(r["road_visible"] for r in inside) if inside else True
            if triage_ok and inside and not road_seen:
                plan.append({"media_id": m["media_id"], "chunk": c["idx"], "concepts": [], "skipped": "no road visible", "counts": {}})
                continue
            flagged = [cid for cid, _ in counts.most_common() if cid not in baseline]
            concepts = list(baseline) + flagged[: max(0, MAX_CONCEPTS_PER_CHUNK - len(baseline))]
            plan.append({"media_id": m["media_id"], "chunk": c["idx"], "concepts": concepts, "counts": dict(counts), "road_frames": sum(1 for r in inside if r["road_visible"]), "frames": len(inside)})
    return plan


def triage(run: Run) -> dict:
    s = get_settings()
    run.set_stage("triage", "running")
    media = run.read("media")
    frames = run.read("frames")
    picked = pick_triage_frames(frames, s.triage_every_s)
    batches = [picked[i : i + BATCH] for i in range(0, len(picked), BATCH)]
    run.log(f"Muse Spark triage: {len(picked)} frames in {len(batches)} batched requests")
    triaged: list[dict] = []
    errors: list[str] = []
    done = 0

    def work(batch):
        return _triage_batch(run, batch)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(work, b) for b in batches]
        for b, fut in zip(batches, futures):
            try:
                res = fut.result()
            except (MetaAPIError, Exception) as exc:  # keep going: baseline prompts still run
                errors.append(str(exc)[:300])
                res = [{"frame_id": f["id"], "media_id": f["media_id"], "frame": f["frame"], "t": f["t"], "path": f["path"], "road_visible": True, "defect_concepts": [], "notes": "triage unavailable", "surface_type": "unknown", "weather": "unknown", "lighting": "unknown", "error": True} for f in b]
            triaged.extend(res)
            done += len(b)
            for r in res:
                run.emit("triage_frame", frame_id=r["frame_id"], media_id=r["media_id"], frame=r["frame"], t=r["t"], concepts=r["defect_concepts"], road_visible=r["road_visible"], notes=r.get("notes"), path=r["path"])
            run.emit("progress", stage="triage", done=done, total=len(picked))

    triage_ok = len(errors) < len(batches)
    plan = plan_for_chunks(media, triaged, baseline_concepts(), triage_ok=triage_ok)
    conditions = Counter((r.get("surface_type"), r.get("weather"), r.get("lighting")) for r in triaged if not r.get("error"))
    out = {"frames": triaged, "plan": plan, "errors": errors, "triage_ok": triage_ok, "conditions": [list(k) + [v] for k, v in conditions.most_common(5)]}
    run.write("triage", out)
    n_jobs = sum(len(p["concepts"]) for p in plan)
    skipped = sum(1 for p in plan if p.get("skipped"))
    if errors:
        run.log(f"Triage had {len(errors)} failed batches; using baseline prompts there", level="warn")
    run.set_stage("triage", "done", frames=len(triaged), sam_jobs=n_jobs, skipped_chunks=skipped, flagged=dict(Counter(c for r in triaged for c in r["defect_concepts"])))
    return out
