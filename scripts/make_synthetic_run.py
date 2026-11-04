"""Build a SYNTHETIC dev run (procedural road, fake Meta client) — for tests and UI
development only. Never used for the demo; the run is named 'synthetic-dev'.

    python scripts/make_synthetic_run.py [--run-id synthetic-dev] [--small]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from mend.config import get_settings  # noqa: E402
from mend.devtools.fake_client import FakeMetaClient  # noqa: E402
from mend.devtools.synthetic import default_scene, render_video  # noqa: E402
from mend.pipeline import set_client  # noqa: E402
from mend.pipeline.runner import run_pipeline  # noqa: E402
from mend.store import Run  # noqa: E402


def build(run_id: str = "synthetic-dev", small: bool = False) -> Run:
    scene = default_scene()
    if small:
        scene.width, scene.height, scene.seconds = 640, 360, 6.0
    cache = get_settings().cache_dir / "synthetic"
    cache.mkdir(parents=True, exist_ok=True)
    video = cache / f"synthetic_{scene.width}x{scene.height}_{scene.seconds:.0f}s.mp4"
    if not video.exists():
        render_video(scene, video)
    run = Run(run_id)
    if run.dir.exists():
        run.delete()
    run = Run.create("SYNTHETIC test road", run_id=run_id, calibration={"preset": "phone_dashboard", "height_m": scene.camera_height_m, "hfov_deg": scene.hfov_deg}, currency="USD", country="synthetic", settings={"synthetic": True, "authority": "Synthetic Test Authority"})
    set_client(FakeMetaClient(scene, run.dir))
    route = [{"lat": 9.05790, "lon": 7.49510}, {"lat": 9.05790 + scene.speed_mps * scene.seconds / 110540, "lon": 7.49510}]
    run_pipeline(run, [video], drawn_route=route)
    return run


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="synthetic-dev")
    ap.add_argument("--small", action="store_true")
    a = ap.parse_args()
    r = build(a.run_id, a.small)
    print("run dir:", r.dir)
