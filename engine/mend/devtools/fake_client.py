"""Deterministic stand-in for MetaClient, used ONLY by tests and the synthetic dev run.

SAM output is real SAM 3.1 wire text generated from the synthetic scene's
ground-truth masks and pushed through Meta's real parser, so everything after
the network boundary is exercised exactly as in production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..config import load_concepts
from ..meta_client import SamResult
from .synthetic import Scene, sam_wire_text


class FakeMetaClient:
    offline = False

    def __init__(self, scene: Scene, run_dir: Path):
        self.scene = scene
        self.run_dir = run_dir
        self.calls: list[tuple[str, Any]] = []

    def _chunk_range(self, media_path: Path) -> tuple[int, int]:
        media = json.loads((self.run_dir / "media.json").read_text())
        for m in media:
            for c in m.get("chunks", []):
                if (self.run_dir / c["path"]).resolve() == Path(media_path).resolve():
                    return c["start"], c["end"]
        raise KeyError(media_path)

    def sam_segment(self, media_kind: str, media_path, prompt: str, *, on_snapshot: Callable | None = None, include_confidence: bool = True, tag: str = "sam") -> SamResult:
        from meta_sam_parser import CompletedOutcome, image_segmentation_format, video_segmentation_format

        self.calls.append(("sam", prompt))
        concepts = {cid for cid, c in load_concepts()["concepts"].items() if c["sam_prompt"] == prompt or prompt in c.get("alt_prompts", [])}
        if prompt == "road crack":
            concepts.add("crack")
        start, end = self._chunk_range(Path(media_path)) if media_kind == "video" else (0, 1)
        text = sam_wire_text(self.scene, concepts, start, end)
        fmt = video_segmentation_format() if media_kind == "video" else image_segmentation_format()
        parser = fmt.create_parser()
        timeline = []
        lines = text.splitlines(keepends=True)
        for i in range(0, len(lines), 5):
            delta = "".join(lines[i : i + 5])
            timeline.append((0.05 * i, delta))
            for snap in parser.push(delta):
                if on_snapshot:
                    on_snapshot(snap)
        fin = parser.finish(CompletedOutcome())
        for snap in fin.events:
            if on_snapshot:
                on_snapshot(snap)
        return SamResult(prompt, media_kind, text, timeline, fin.result, None, False, 0.1)

    def spark_json(self, messages, schema, *, name="result", model=None, reasoning_effort=None, tag="json") -> dict:
        self.calls.append(("spark_json", name))
        if name == "triage":
            n = sum(1 for m in messages for p in (m.get("content") if isinstance(m.get("content"), list) else []) if p.get("type") == "image_url")
            return {
                "frames": [
                    {"index": i, "road_visible": True, "surface_type": "asphalt", "weather": "clear", "lighting": "day", "defect_concepts": ["pothole", "standing_water"], "notes": "synthetic"}
                    for i in range(n)
                ]
            }
        if name == "crop_judgement":
            ids = _ids_in(messages)
            return {"defects": [{"id": i, "is_defect": True, "depth": "moderate", "severity": 3, "edge_condition": "ragged", "notes": "synthetic"} for i in ids]}
        if name == "site_rationale":
            ids = _ids_in(messages)
            return {"sites": [{"site_id": i, "rationale": f"Synthetic rationale for {i}."} for i in ids]}
        if name == "tender_sections":
            return {"executive_summary": "Synthetic summary.", "scope_of_works": "Synthetic scope.", "technical_specifications": "Synthetic specs.", "programme": "Synthetic programme.", "safety_and_traffic_management": "Synthetic safety.", "evidence_note": "Synthetic evidence."}
        if name == "voice_intent":
            return {"summary": "Children cross here every morning.", "tags": ["school_crossing"], "near_school": True, "near_hospital": False, "near_bus_stop": False, "heavy_traffic": False, "exposure_multiplier": 1.5, "urgency": "high"}
        if name == "camera":
            return {"horizon_y_frac": 0.4, "camera_mount": "dashboard", "confidence": "medium", "notes": "synthetic"}
        return {}

    def spark_chat(self, messages, **kwargs) -> dict:
        self.calls.append(("spark_chat", kwargs.get("tag")))
        return {"choices": [{"message": {"role": "assistant", "content": "Synthetic answer citing D001.", "tool_calls": None}}], "usage": None}

    def transcribe(self, audio_path, **kwargs) -> dict:
        return {"text": "Kids cross here every morning on the way to school.", "model": "fake", "transport": "fake"}


def _ids_in(messages) -> list[str]:
    import re

    text = json.dumps(messages)
    return sorted(set(re.findall(r'\b([DS]\d{3})\b', text)))
