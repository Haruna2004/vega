"""Runs the stages in order, as a CLI call or a background job from the UI."""

from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from ..meta_client import current_run_dir
from ..store import STAGES, Run

_jobs: dict[str, threading.Thread] = {}


def stage_fn(name: str) -> Callable[[Run], object]:
    from . import geo, measure, prioritize, render, report, segment, triage

    return {
        "triage": triage.triage,
        "segment": segment.segment,
        "measure": measure.measure,
        "geo": geo.geo,
        "prioritize": prioritize.prioritize,
        "report": report.report,
        "render": render.render,
    }[name]


def run_pipeline(run: Run, inputs: list[Path] | None = None, *, from_stage: str = "ingest", to_stage: str = "render", drawn_route: list[dict] | None = None, start_s: float | None = None, max_seconds: float | None = None) -> None:
    from .ingest import ingest

    token = current_run_dir.set(run.dir)
    try:
        if from_stage == "ingest":
            run.reset_events()
        run.update_meta(status="running", error=None)
        run.emit("run", status="running", from_stage=from_stage)
        t0 = time.time()
        started = False
        for name in STAGES:
            if name == from_stage:
                started = True
            if not started:
                continue
            try:
                if name == "ingest":
                    ingest(run, inputs or [], drawn_route=drawn_route, start_s=start_s, max_seconds=max_seconds)
                else:
                    stage_fn(name)(run)
            except Exception as exc:
                run.set_stage(name, "failed", error=f"{type(exc).__name__}: {exc}"[:800])
                run.log(traceback.format_exc()[-2000:], level="error")
                raise
            if name == to_stage:
                break
        elapsed = time.time() - t0
        run.update_meta(status="done", processing_s=round(elapsed, 1), finished_at=time.time())
        run.emit("run", status="done", processing_s=round(elapsed, 1))
    except Exception as exc:
        run.update_meta(status="failed", error=f"{type(exc).__name__}: {exc}"[:800])
        run.emit("run", status="failed", error=str(exc)[:500])
        raise
    finally:
        current_run_dir.reset(token)


def start_background(run: Run, inputs: list[Path] | None = None, **kwargs) -> None:
    def target():
        try:
            run_pipeline(run, inputs, **kwargs)
        except Exception:
            pass  # status + traceback are already in run.json / events.jsonl

    th = threading.Thread(target=target, name=f"run-{run.id}", daemon=True)
    _jobs[run.id] = th
    th.start()


def is_running(run_id: str) -> bool:
    th = _jobs.get(run_id)
    return bool(th and th.is_alive())
