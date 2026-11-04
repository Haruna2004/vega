"""Smoke test for the Meta Model API: one call per model we depend on.

    python scripts/smoke_meta_api.py [--image path.jpg] [--video path.mp4] [--audio note.m4a]

Prints raw responses and writes them to docs/api_shapes.md so the client code
can be checked against reality. Every call is cached, so re-running is free.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from mend.config import get_settings  # noqa: E402
from mend.meta_client import data_url, get_client  # noqa: E402

OUT = ROOT / "docs" / "api_shapes.md"


def _default_image() -> Path:
    for p in sorted((ROOT / "data" / "samples").glob("*.jpg")):
        return p
    raise SystemExit("no sample image; pass --image")


def _make_video(image: Path) -> Path:
    """3-second clip panning across the sample image, so SAM has something to track."""
    out = Path(tempfile.mkdtemp()) / "smoke.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(image), "-t", "3", "-r", "10",
         "-vf", "scale=1280:-2,crop=960:540:'(iw-960)*t/3':'(ih-540)/2'", "-pix_fmt", "yuv420p", str(out)],
        check=True,
    )
    return out


def _make_audio() -> Path | None:
    out = Path(tempfile.mkdtemp()) / "note.wav"
    try:
        subprocess.run(["espeak", "-w", str(out), "Kids cross here every morning near the primary school."], check=True, capture_output=True)
        return out
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path)
    ap.add_argument("--video", type=Path)
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--prompt", default="pothole")
    args = ap.parse_args()

    s = get_settings()
    if not s.has_key:
        raise SystemExit("META_MODEL_API_KEY is not set")
    client = get_client()
    image = args.image or _default_image()
    sections: list[str] = [f"# Meta Model API shapes (captured {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})\n", f"Base URL: `{s.base_url}`\n"]

    def record(title: str, fn):
        print(f"\n=== {title} ===")
        try:
            out = fn()
            text = json.dumps(out, indent=2, ensure_ascii=False, default=str)
            print(text[:4000])
            sections.append(f"## {title}\n\n```json\n{text[:12000]}\n```\n")
        except Exception as exc:
            tb = traceback.format_exc()
            print(tb)
            sections.append(f"## {title} — FAILED\n\n```\n{exc}\n{tb[-3000:]}\n```\n")

    # 1. Muse Spark: image + strict JSON schema
    def spark():
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"road_visible": {"type": "boolean"}, "defects": {"type": "array", "items": {"type": "string"}}, "notes": {"type": "string"}},
            "required": ["road_visible", "defects", "notes"],
        }
        msgs = [{"role": "user", "content": [{"type": "text", "text": "Is a road visible? List visible road defects."}, {"type": "image_url", "image_url": {"url": data_url(image)}}]}]
        raw = client.spark_chat(msgs, response_format={"type": "json_schema", "json_schema": {"name": "triage", "strict": True, "schema": schema}}, reasoning_effort="low", tag="smoke")
        return raw

    record("Muse Spark chat.completions (image + json_schema)", spark)

    # 2. SAM 3.1 image
    def sam_image():
        res = client.sam_segment("image", image, args.prompt, tag="smoke")
        return {"cached": res.cached, "duration_s": res.duration_s, "usage": res.usage, "events_sample": res.events_sample, "raw_text_head": res.raw_text[:1500], "n_records": len(res.result.records), "diagnostics": [str(d) for d in res.result.diagnostics][:5]}

    record(f"SAM 3.1 image ('{args.prompt}')", sam_image)

    # 3. SAM 3.1 video
    def sam_video():
        video = args.video or _make_video(image)
        res = client.sam_segment("video", video, args.prompt, tag="smoke")
        return {"cached": res.cached, "duration_s": res.duration_s, "usage": res.usage, "events_sample": res.events_sample, "raw_text_head": res.raw_text[:1500], "n_records": len(res.result.records), "n_deltas": len(res.timeline)}

    record(f"SAM 3.1 video ('{args.prompt}')", sam_video)

    # 4. Muse Voice Transcribe
    def asr():
        audio = args.audio or _make_audio()
        if audio is None:
            return {"skipped": "no audio given and espeak not installed; pass --audio"}
        return client.transcribe(audio)

    record("Muse Voice Transcribe (realtime websocket)", asr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(sections))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
