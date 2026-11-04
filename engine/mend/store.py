"""Run directory store. JSON-per-stage files are the source of truth."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from .config import get_settings

STAGES = ["ingest", "triage", "segment", "measure", "geo", "prioritize", "report", "render"]

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(run_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(run_id, threading.Lock())


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return text[:40] or "run"


class Run:
    def __init__(self, run_id: str, root: Path | None = None):
        self.id = run_id
        self.root = root or get_settings().runs_dir
        self.dir = self.root / run_id
        self._t0: float | None = None

    # ------------------------------------------------------------ lifecycle
    @classmethod
    def create(cls, name: str, *, calibration: dict | None = None, currency: str = "USD", country: str = "", run_id: str | None = None, settings: dict | None = None) -> "Run":
        root = get_settings().runs_dir
        run_id = run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(name)}"
        run = cls(run_id, root)
        run.dir.mkdir(parents=True, exist_ok=True)
        for sub in ("inputs", "frames", "chunks", "evidence", "workorders", "voice"):
            (run.dir / sub).mkdir(exist_ok=True)
        meta = {
            "id": run_id,
            "name": name,
            "created_at": time.time(),
            "status": "created",
            "calibration": calibration or {},
            "currency": currency,
            "country": country,
            "settings": settings or {},
            "stages": {s: {"status": "pending"} for s in STAGES},
            "inputs": [],
            "gps_source": None,
        }
        run.write("run", meta)
        return run

    @classmethod
    def load(cls, run_id: str) -> "Run":
        run = cls(run_id)
        if not (run.dir / "run.json").exists():
            from . import r2sync

            if not r2sync.hydrate_run(run_id, run.root) or not (run.dir / "run.json").exists():
                raise FileNotFoundError(run_id)
        return run

    @classmethod
    def list(cls) -> list[dict]:
        root = get_settings().runs_dir
        out = []
        if not root.exists():
            return out
        for d in sorted(root.iterdir(), reverse=True):
            meta_path = d / "run.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    summary = {}
                    if (d / "summary.json").exists():
                        summary = json.loads((d / "summary.json").read_text())
                    out.append({**{k: meta.get(k) for k in ("id", "name", "created_at", "status", "currency", "country", "gps_source")}, "summary": summary})
                except Exception:
                    continue
        return out

    def delete(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    # ------------------------------------------------------------ json io
    def path(self, name: str) -> Path:
        return self.dir / (name if "." in name else f"{name}.json")

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def read(self, name: str, default: Any = None) -> Any:
        p = self.path(name)
        if not p.exists():
            return default
        return json.loads(p.read_text())

    def write(self, name: str, data: Any) -> Path:
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=None, separators=(",", ":")))
        tmp.replace(p)
        return p

    @property
    def meta(self) -> dict:
        return self.read("run", {})

    def update_meta(self, **changes: Any) -> dict:
        with _lock_for(self.id):
            meta = self.meta
            meta.update(changes)
            self.write("run", meta)
        if changes.get("status") in ("done", "failed", "running"):
            from . import r2sync

            r2sync.sync_run(self)
        return meta

    def set_stage(self, stage: str, status: str, **info: Any) -> None:
        with _lock_for(self.id):
            meta = self.meta
            st = meta.setdefault("stages", {}).setdefault(stage, {})
            st["status"] = status
            now = time.time()
            if status == "running":
                st["started_at"] = now
                st.pop("error", None)
            if status in ("done", "failed", "skipped"):
                st["finished_at"] = now
            st.update(info)
            self.write("run", meta)
        self.emit("stage", stage=stage, status=status, **info)
        if status in ("done", "failed"):
            from . import r2sync

            r2sync.sync_run(self)

    # ------------------------------------------------------------ events
    def emit(self, type_: str, **data: Any) -> None:
        """Append one event to events.jsonl (the live view tails this file)."""
        if self._t0 is None:
            self._t0 = self.meta.get("started_at") or time.time()
        event = {"t": round(time.time() - self._t0, 3), "type": type_, **data}
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with _lock_for(self.id + ":events"):
            with open(self.dir / "events.jsonl", "a") as fh:
                fh.write(line + "\n")

    def reset_events(self) -> None:
        p = self.dir / "events.jsonl"
        if p.exists():
            p.unlink()
        self._t0 = time.time()
        self.update_meta(started_at=self._t0)

    def log(self, message: str, level: str = "info", **extra: Any) -> None:
        self.emit("log", level=level, message=message, **extra)

    # ------------------------------------------------------------ urls
    def rel(self, path: Path | str) -> str:
        """Path relative to the run dir (used to build /files URLs)."""
        return str(Path(path).resolve().relative_to(self.dir.resolve()))
