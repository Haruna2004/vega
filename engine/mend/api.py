"""FastAPI app: run management, data, files (range-capable), live events (SSE),
voice notes, unit-rate editing, the Ask agent, exports, and the static frontend."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .camera import CAMERA_PRESETS
from .config import REPO_ROOT, get_settings, load_concepts, load_unit_rates
from .pipeline import runner
from .store import STAGES, Run

app = FastAPI(title="MEND API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PUBLIC_JSON = {"run", "media", "frames", "triage", "defects", "sites", "boq", "documents", "calibration", "route", "summary", "annotated", "voice_notes", "tender_sections", "unit_rates"}


def _run(run_id: str) -> Run:
    try:
        return Run.load(run_id)
    except FileNotFoundError:
        raise HTTPException(404, f"run {run_id} not found")


# ---------------------------------------------------------------- meta
@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    from .simulate import provider_name

    return {"ok": True, "provider": provider_name(), "offline": s.offline, "has_key": s.has_key, "models": {"spark": s.spark_model, "sam": s.sam_model, "asr": s.asr_model}, "time": time.time()}


@app.get("/api/config")
def config() -> dict:
    c = load_concepts()
    return {"concepts": c["concepts"], "severity_colors": c["severity_colors"], "camera_presets": CAMERA_PRESETS, "unit_rates": load_unit_rates(), "stages": STAGES}


# ---------------------------------------------------------------- runs
@app.get("/api/runs")
def list_runs() -> list[dict]:
    return Run.list()


@app.post("/api/runs")
async def create_run(
    files: list[UploadFile] = File(...),
    name: str = Form("Road survey"),
    calibration: str = Form("{}"),
    currency: str = Form("USD"),
    country: str = Form(""),
    authority: str = Form(""),
    route: str = Form(""),
    max_seconds: float = Form(0),
    start_s: float = Form(0),
) -> dict:
    run = Run.create(name, calibration=json.loads(calibration or "{}"), currency=currency, country=country, settings={"authority": authority or None, "max_seconds": max_seconds or None})
    saved = []
    for f in files:
        dst = run.dir / "inputs" / Path(f.filename or "upload.bin").name
        with open(dst, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(dst)
    drawn = json.loads(route) if route else None
    runner.start_background(run, saved, drawn_route=drawn, start_s=start_s or None, max_seconds=max_seconds or None)
    return {"id": run.id}


@app.post("/api/runs/from-path")
async def create_run_from_path(payload: dict) -> dict:
    """Start a run on files already in data/raw (no upload; handy for big videos)."""
    raw = get_settings().data_dir / "raw"
    paths = [raw / Path(p).name for p in payload.get("files", [])]
    missing = [str(p) for p in paths if not p.exists()]
    if missing or not paths:
        raise HTTPException(400, f"missing files: {missing}")
    run = Run.create(payload.get("name") or "Road survey", calibration=payload.get("calibration") or {}, currency=payload.get("currency", "USD"), country=payload.get("country", ""), settings={"authority": payload.get("authority"), "max_seconds": payload.get("max_seconds")}, run_id=payload.get("run_id"))
    runner.start_background(run, paths, drawn_route=payload.get("route"), start_s=payload.get("start_s"), max_seconds=payload.get("max_seconds"))
    return {"id": run.id}


@app.get("/api/raw")
def list_raw() -> list[dict]:
    raw = get_settings().data_dir / "raw"
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(raw.glob("*")) if p.is_file() and not p.name.startswith(".")]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = _run(run_id)
    meta = run.meta
    meta["running"] = runner.is_running(run_id)
    meta["summary"] = run.read("summary", {})
    return meta


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str) -> dict:
    if run_id == "demo":
        raise HTTPException(400, "refusing to delete the demo run")
    _run(run_id).delete()
    return {"ok": True}


@app.get("/api/runs/{run_id}/data/{name}")
def get_data(run_id: str, name: str) -> Any:
    run = _run(run_id)
    if name not in PUBLIC_JSON and not name.startswith("overlays_"):
        raise HTTPException(404, name)
    if not run.exists(name):
        raise HTTPException(404, f"{name} not ready")
    return FileResponse(run.path(name), media_type="application/json")


@app.get("/api/runs/{run_id}/tracks")
def get_tracks(run_id: str) -> dict:
    """Track list without mask payloads (detections.json is large)."""
    det = _run(run_id).read("detections", {})
    tracks = [{k: v for k, v in t.items() if k != "dets"} for t in det.get("tracks", [])]
    return {"tracks": tracks, "dropped": det.get("dropped", []), "jobs": det.get("jobs", [])}


@app.get("/api/runs/{run_id}/files/{path:path}")
def get_file(run_id: str, path: str) -> FileResponse:
    run = _run(run_id)
    target = (run.dir / path).resolve()
    if not str(target).startswith(str(run.dir.resolve())) or not target.is_file():
        raise HTTPException(404, path)
    return FileResponse(target)


@app.get("/api/runs/{run_id}/costs")
def get_costs(run_id: str) -> dict:
    run = _run(run_id)
    p = run.dir / "costs.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
    by_kind: dict[str, dict] = {}
    for r in rows:
        k = by_kind.setdefault(r["kind"], {"calls": 0, "cached": 0, "est_cost_usd": 0.0})
        k["calls"] += 1
        k["cached"] += 1 if r.get("cached") else 0
        k["est_cost_usd"] = round(k["est_cost_usd"] + (r.get("est_cost_usd") or 0), 5)
    return {"by_kind": by_kind, "api_calls": sum(1 for r in rows if not r.get("cached")), "cache_hits": sum(1 for r in rows if r.get("cached")), "est_cost_usd": round(sum(r.get("est_cost_usd") or 0 for r in rows), 4)}


# ---------------------------------------------------------------- live events (SSE)
@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request, replay: int = 0, speed: float = 1.0, max_gap: float = 1.5) -> StreamingResponse:
    """Server-sent events from events.jsonl.

    Live runs are tailed. `replay=1` re-emits a finished run's log with its original
    timing divided by `speed` (gaps capped at `max_gap` seconds of wall time)."""
    run = _run(run_id)
    path = run.dir / "events.jsonl"

    async def gen():
        pos = 0
        last_t = None
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                return
            if path.exists():
                with open(path) as fh:
                    fh.seek(pos)
                    chunk = fh.read()
                    pos = fh.tell()
                lines = chunk.splitlines(keepends=True)
                if lines and not lines[-1].endswith("\n"):
                    pos -= len(lines[-1])
                    lines = lines[:-1]
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if replay:
                        try:
                            t = json.loads(line).get("t", 0)
                        except json.JSONDecodeError:
                            t = last_t or 0
                        if last_t is not None and t > last_t:
                            await asyncio.sleep(min(max_gap, (t - last_t) / max(speed, 0.01)))
                        last_t = t
                    yield f"data: {line}\n\n"
            running = runner.is_running(run_id) or run.meta.get("status") == "running"
            if not running and (replay or path.exists()):
                yield 'data: {"type":"eof"}\n\n'
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- actions
@app.post("/api/runs/{run_id}/route")
def set_route(run_id: str, payload: dict) -> dict:
    from .pipeline.geo import set_drawn_route

    run = _run(run_id)
    set_drawn_route(run, payload["media_id"], payload["points"])
    runner.start_background(run, None, from_stage="geo", to_stage="report")
    return {"ok": True}


@app.post("/api/runs/{run_id}/rerun")
def rerun(run_id: str, payload: dict) -> dict:
    run = _run(run_id)
    stage = payload.get("from_stage", "measure")
    if stage not in STAGES or stage == "ingest":
        raise HTTPException(400, f"bad stage {stage}")
    runner.start_background(run, None, from_stage=stage, to_stage=payload.get("to_stage", "render"))
    return {"ok": True}


@app.post("/api/runs/{run_id}/voice")
async def voice(run_id: str, audio: UploadFile | None = File(None), target_kind: str = Form("site"), target_id: str = Form(...), text: str = Form("")) -> dict:
    from .meta_client import current_run_dir
    from .pipeline.voice import add_voice_note

    run = _run(run_id)
    tmp_path = None
    if audio is not None:
        suffix = Path(audio.filename or "note.webm").suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(audio.file, tmp)
            tmp_path = Path(tmp.name)
    token = current_run_dir.set(run.dir)
    try:
        return await asyncio.to_thread(add_voice_note, run, target_kind, target_id, tmp_path, typed_text=text or None)
    except Exception as exc:
        raise HTTPException(502, f"voice note failed: {exc}")
    finally:
        current_run_dir.reset(token)
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


@app.post("/api/runs/{run_id}/ask")
async def ask(run_id: str, payload: dict) -> dict:
    from .meta_client import current_run_dir
    from .pipeline.agent import ask as agent_ask

    run = _run(run_id)
    token = current_run_dir.set(run.dir)
    try:
        return await asyncio.to_thread(agent_ask, run, payload["question"], payload.get("history"))
    except Exception as exc:
        raise HTTPException(502, f"agent failed: {exc}")
    finally:
        current_run_dir.reset(token)


@app.get("/api/runs/{run_id}/rates")
def get_rates(run_id: str) -> dict:
    from .pipeline.report import effective_rates

    return effective_rates(_run(run_id))


@app.put("/api/runs/{run_id}/rates")
async def put_rates(run_id: str, payload: dict, pdf: int = 1) -> dict:
    from .pipeline.report import build_documents

    run = _run(run_id)
    run.write("unit_rates", payload)
    out = await asyncio.to_thread(build_documents, run, pdf=bool(pdf))
    summary = run.read("summary", {})
    summary["total_cost"] = out["boq"]["total"]
    summary["currency"] = out["boq"]["currency"]
    summary["symbol"] = out["boq"]["symbol"]
    run.write("summary", summary)
    return out


@app.delete("/api/runs/{run_id}/rates")
async def reset_rates(run_id: str) -> dict:
    from .pipeline.report import build_documents

    run = _run(run_id)
    p = run.path("unit_rates")
    if p.exists():
        p.unlink()
    out = await asyncio.to_thread(build_documents, run, pdf=True)
    return out


@app.get("/api/runs/{run_id}/export/geojson")
def export_geojson(run_id: str) -> JSONResponse:
    run = _run(run_id)
    defects = run.read("defects", [])
    sites = {s["id"]: s for s in run.read("sites", [])}
    feats = []
    for d in defects:
        if d.get("lat") is None:
            continue
        props = {k: d.get(k) for k in ("id", "site_id", "label", "concept", "severity", "area_m2", "length_m", "conf_low", "conf_high", "method", "position", "dismissed")}
        s = sites.get(d.get("site_id") or "")
        if s:
            props.update({"site_rank": s.get("rank"), "priority_score": s.get("priority_score"), "street": s.get("street")})
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [d["lon"], d["lat"]]}, "properties": props})
    return JSONResponse({"type": "FeatureCollection", "features": feats}, headers={"Content-Disposition": f'attachment; filename="{run_id}-defects.geojson"'})


@app.get("/api/runs/{run_id}/export/csv")
def export_csv(run_id: str) -> Response:
    run = _run(run_id)
    buf = io.StringIO()
    cols = ["id", "site_id", "label", "severity", "area_m2", "length_m", "conf_low", "conf_high", "method", "position", "lat", "lon", "t", "dismissed"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for d in run.read("defects", []):
        w.writerow(d)
    return PlainTextResponse(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{run_id}-defects.csv"'})


# ---------------------------------------------------------------- frontend (SPA)
FRONTEND = REPO_ROOT / "frontend" / "dist"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND / "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (FRONTEND / path).resolve()
        if path and str(f).startswith(str(FRONTEND.resolve())) and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND / "index.html")
