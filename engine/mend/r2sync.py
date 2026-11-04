"""Mirror run folders and the API cache to Cloudflare R2 through the edge Worker.

The engine's disk on Cloud Run is temporary. After every pipeline stage the run
folder is pushed to R2 (only changed files); a run missing locally is pulled
back on demand. The Worker serves results to browsers straight from R2.

Enabled when MEND_EDGE_URL and MEND_ENGINE_KEY are set; a no-op otherwise.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

import httpx

log = logging.getLogger("mend.r2")
_lock = threading.Lock()
_sent: dict[str, float] = {}


def enabled() -> bool:
    return bool(os.environ.get("MEND_EDGE_URL") and os.environ.get("MEND_ENGINE_KEY"))


def _client() -> httpx.Client:
    return httpx.Client(base_url=os.environ["MEND_EDGE_URL"].rstrip("/"), headers={"x-mend-key": os.environ["MEND_ENGINE_KEY"]}, timeout=300)


def put_file(key: str, path: Path) -> None:
    with _client() as c, open(path, "rb") as fh:
        r = c.put(f"/internal/r2/{key}", content=fh.read())
        r.raise_for_status()


def put_json(key: str, data) -> None:
    with _client() as c:
        c.put(f"/internal/r2/{key}", content=json.dumps(data).encode()).raise_for_status()


def get_bytes(key: str) -> bytes | None:
    with _client() as c:
        r = c.get(f"/internal/r2/{key}")
        return r.content if r.status_code == 200 else None


def list_keys(prefix: str) -> list[dict]:
    with _client() as c:
        r = c.get("/internal/list", params={"prefix": prefix})
        r.raise_for_status()
        return r.json()


def sync_dir(local: Path, prefix: str) -> int:
    """Upload files whose mtime changed since the last sync."""
    if not enabled() or not local.exists():
        return 0
    n = 0
    with _lock:
        for p in sorted(local.rglob("*")):
            if not p.is_file() or p.suffix == ".tmp" or ".tmp" in p.name:
                continue
            key = f"{prefix}/{p.relative_to(local).as_posix()}"
            m = p.stat().st_mtime
            if _sent.get(key) == m:
                continue
            try:
                put_file(key, p)
                _sent[key] = m
                n += 1
            except Exception as exc:  # keep processing; next sync retries
                log.warning("r2 put %s failed: %s", key, exc)
    return n


def sync_run(run) -> None:
    if not enabled():
        return
    sync_dir(run.dir, f"runs/{run.id}")
    write_index()


def write_index() -> None:
    from .store import Run

    try:
        # merge with the index in R2: a fresh Cloud Run instance only has some runs on disk
        remote = json.loads(get_bytes("index.json") or b"[]")
        local = {r["id"]: r for r in Run.list()}
        merged = list(local.values()) + [r for r in remote if r["id"] not in local]
        merged.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
        put_json("index.json", merged)
    except Exception as exc:
        log.warning("index sync failed: %s", exc)


HEAVY = (".mp4", ".webm", ".mov")
HEAVY_DIRS = ("/frames/", "/chunks/", "/inputs/")


def hydrate_run(run_id: str, root: Path, full: bool = False) -> bool:
    """Download a run folder from R2 if it is not on local disk.

    Light mode (default) skips video, frames and chunks: Ask, voice notes and
    rate edits only need the JSON and evidence images, so a cold instance can
    answer in a second instead of pulling ~70 MB first. Reprocessing asks for full."""
    from concurrent.futures import ThreadPoolExecutor

    if not enabled():
        return False
    keys = list_keys(f"runs/{run_id}/")
    if not keys:
        return False
    if not full:
        keys = [k for k in keys if not k["key"].endswith(HEAVY) and not any(d in k["key"] for d in HEAVY_DIRS)]

    def fetch(k):
        dst = root / k["key"][len("runs/") :]
        if dst.exists() and dst.stat().st_size == k["size"]:
            return
        data = get_bytes(k["key"])
        if data is None:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        _sent[k["key"]] = dst.stat().st_mtime

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(fetch, keys))
    return True


def cache_get(kind: str, rel: str) -> dict | None:
    if not enabled():
        return None
    try:
        data = get_bytes(f"cache/{kind}/{rel}")
        return json.loads(data) if data else None
    except Exception:
        return None


def cache_put(kind: str, rel: str, value: dict) -> None:
    if not enabled():
        return
    threading.Thread(target=lambda: _safe_put(f"cache/{kind}/{rel}", value), daemon=True).start()


def _safe_put(key: str, value) -> None:
    try:
        put_json(key, value)
    except Exception as exc:
        log.warning("cache sync %s failed: %s", key, exc)
