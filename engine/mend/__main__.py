"""CLI.

    python -m mend serve [--port 8000]
    python -m mend run data/raw/drive.mp4 [--name "Kano ring road"] [--route route.gpx] [--run-id demo]
    python -m mend stage <run_id> <stage>           # rerun one stage (triage|segment|measure|geo|prioritize|report|render)
    python -m mend from <run_id> <stage>            # rerun from a stage to the end
    python -m mend route <run_id> <media_id> lat,lon lat,lon ...
    python -m mend ask <run_id> "question"
    python -m mend voice <run_id> <site_id> note.m4a
    python -m mend runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .meta_client import current_run_dir
from .store import STAGES, Run


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="mend")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p = sub.add_parser("run")
    p.add_argument("inputs", nargs="+", type=Path)
    p.add_argument("--name", default=None)
    p.add_argument("--run-id", default=None)
    p.add_argument("--route", type=Path, default=None, help="GPX or CSV route")
    p.add_argument("--waypoints", default=None, help='drawn route as "lat,lon;lat,lon;..."')
    p.add_argument("--preset", default="phone_dashboard")
    p.add_argument("--height", type=float, default=None, help="camera height (m)")
    p.add_argument("--hfov", type=float, default=None, help="horizontal FOV (deg)")
    p.add_argument("--horizon", type=float, default=None, help="horizon row as fraction of height")
    p.add_argument("--currency", default="USD")
    p.add_argument("--country", default="")
    p.add_argument("--authority", default=None)
    p.add_argument("--start", type=float, default=None, help="trim: start second")
    p.add_argument("--max-seconds", type=float, default=None, help="trim: max seconds per video")
    p.add_argument("--to-stage", default="render", choices=STAGES)
    p = sub.add_parser("stage")
    p.add_argument("run_id")
    p.add_argument("stage", choices=STAGES[1:])
    p = sub.add_parser("from")
    p.add_argument("run_id")
    p.add_argument("stage", choices=STAGES[1:])
    p = sub.add_parser("route")
    p.add_argument("run_id")
    p.add_argument("media_id")
    p.add_argument("points", nargs="+")
    p = sub.add_parser("ask")
    p.add_argument("run_id")
    p.add_argument("question")
    p = sub.add_parser("voice")
    p.add_argument("run_id")
    p.add_argument("site_id")
    p.add_argument("audio", type=Path)
    sub.add_parser("runs")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("mend.api:app", host=a.host, port=a.port, log_level="info")
        return
    if a.cmd == "runs":
        for r in Run.list():
            print(f"{r['id']:40s} {r['status']:8s} {r.get('summary') or ''}")
        return
    if a.cmd == "run":
        from .pipeline.runner import run_pipeline

        cal = {"preset": a.preset}
        if a.height:
            cal["height_m"] = a.height
        if a.hfov:
            cal["hfov_deg"] = a.hfov
        if a.horizon:
            cal["horizon_y_frac"] = a.horizon
        name = a.name or a.inputs[0].stem
        if a.run_id and Run(a.run_id).dir.exists():
            Run(a.run_id).delete()
        run = Run.create(name, run_id=a.run_id, calibration=cal, currency=a.currency, country=a.country, settings={"authority": a.authority, "max_seconds": a.max_seconds})
        drawn = None
        if a.waypoints:
            drawn = [{"lat": float(x.split(",")[0]), "lon": float(x.split(",")[1])} for x in a.waypoints.split(";") if x.strip()]
        inputs = list(a.inputs) + ([a.route] if a.route else [])
        run_pipeline(run, inputs, drawn_route=drawn, start_s=a.start, max_seconds=a.max_seconds, to_stage=a.to_stage)
        print(json.dumps(run.read("summary", {}), indent=1))
        print("run:", run.id)
        return
    run = Run.load(a.run_id)
    token = current_run_dir.set(run.dir)
    try:
        if a.cmd == "stage":
            from .pipeline.runner import stage_fn

            stage_fn(a.stage)(run)
        elif a.cmd == "from":
            from .pipeline.runner import run_pipeline

            run_pipeline(run, None, from_stage=a.stage)
        elif a.cmd == "route":
            from .pipeline.geo import set_drawn_route
            from .pipeline.runner import run_pipeline

            pts = [{"lat": float(p.split(",")[0]), "lon": float(p.split(",")[1])} for p in a.points]
            set_drawn_route(run, a.media_id, pts)
            run_pipeline(run, None, from_stage="geo", to_stage="report")
        elif a.cmd == "ask":
            from .pipeline.agent import ask

            print(json.dumps(ask(run, a.question), indent=1, ensure_ascii=False))
        elif a.cmd == "voice":
            from .pipeline.voice import add_voice_note

            out = add_voice_note(run, "site", a.site_id, a.audio)
            print(json.dumps({k: out[k] for k in ("site_id", "old_rank", "new_rank")} | {"transcript": out["note"]["transcript"], "intent": out["note"]["intent"]}, indent=1))
    finally:
        current_run_dir.reset(token)


if __name__ == "__main__":
    sys.exit(main())
