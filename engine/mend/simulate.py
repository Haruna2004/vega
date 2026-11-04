"""SIMULATED Meta models — used only when no API key is configured.

>>> THIS IS THE ONLY PLACE WHERE AI IS SIMULATED. <<<
Switch: env MEND_PROVIDER=meta (real) | simulate. Default: `meta` when
META_MODEL_API_KEY is set, otherwise `simulate`. Nothing else changes.

What each simulated call does instead of the real model:
- sam_segment (SAM 3.1): classical computer vision on the actual video frames
  (dark-blob / thin-dark-line detection on the road area + IoU tracking). The
  result is encoded in the exact SAM 3.1 wire format and pushed through Meta's
  real parser, so everything downstream runs unchanged.
- spark_json / spark_chat (Muse Spark): deterministic rules and templates that
  return the same JSON shapes the prompts ask for.
- transcribe (Muse Voice Transcribe): cannot hear audio; returns a placeholder
  (the UI lets you type the note instead).

Every output carries `simulated: true` and the run records provider=simulate,
so the UI shows a SIMULATED badge.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from .meta_client import SamResult

SIM_DELAY = 0.04  # seconds between streamed deltas, to mimic SAM's stream


# ----------------------------------------------------------------- vision
def _road_roi(h: int, w: int) -> np.ndarray:
    """Trapezoid below the horizon where a road usually is."""
    roi = np.zeros((h, w), np.uint8)
    top = int(h * 0.55)
    pts = np.array([[int(w * 0.30), top], [int(w * 0.70), top], [int(w * 0.98), h - 1], [int(w * 0.02), h - 1]], np.int32)
    cv2.fillPoly(roi, [pts], 1)
    return roi


def _candidates(frame: np.ndarray, kind: str) -> list[np.ndarray]:
    """Binary masks of dark blobs (pothole-like) or thin dark lines (crack-like)."""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    roi = _road_roi(h, w)
    if kind == "crack":
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, k)
        _, m = cv2.threshold(bh, 28, 1, cv2.THRESH_BINARY)
    else:
        local = cv2.blur(gray, (61, 61)).astype(np.int16)
        m = ((local - gray.astype(np.int16)) > 26).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    m &= roi
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, bw, bh_, area = stats[i]
        if kind == "crack":
            if area < 60 or max(bw, bh_) < 0.06 * w or area > 0.02 * h * w:
                continue
            if area / float(bw * bh_) > 0.35:  # lines are sparse in their box
                continue
        else:
            if area < 0.0006 * h * w or area > 0.03 * h * w:
                continue
            if bw > 4 * bh_ or bh_ > 3 * bw:  # skip long shadows / markings
                continue
        out.append(lab == i)
    return out[:6]


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return inter / union if union else 0.0


def simulate_sam_wire(video_or_image: Path, prompt: str, media_kind: str) -> str:
    from .devtools.synthetic import encode_record

    kind = "crack" if "crack" in prompt else "pothole" if "pothole" in prompt or "manhole" in prompt else None
    if kind is None:  # puddles, signs, etc.: nothing simulated
        return ""
    frames: list[np.ndarray] = []
    if media_kind == "image":
        img = cv2.imread(str(video_or_image))
        if img is not None:
            frames = [img]
    else:
        cap = cv2.VideoCapture(str(video_or_image))
        while True:
            ok, img = cap.read()
            if not ok:
                break
            frames.append(img)
        cap.release()
    tracks: list[dict] = []  # {id, mask, last}
    next_id = 1
    lines = []
    for fi, img in enumerate(frames):
        recs = []
        for m in _candidates(img, kind):
            best = max(tracks, key=lambda t: _iou(t["mask"], m) if fi - t["last"] <= 3 else -1, default=None)
            if best is not None and fi - best["last"] <= 3 and _iou(best["mask"], m) > 0.2:
                tid = best["id"]
                best.update(mask=m, last=fi)
            else:
                tid = next_id
                next_id += 1
                tracks.append({"id": tid, "mask": m, "last": fi})
            rec = encode_record(tid, m, 0.6 + 0.3 * ((tid * 37) % 10) / 10)
            if rec:
                recs.append(rec)
        if recs:
            lines.append(f"<{fi}f>" + ",".join(recs))
    return "\n".join(lines) + ("\n" if lines else "")


# ----------------------------------------------------------------- client
class SimulatedMetaClient:
    offline = False
    provider = "simulate"

    def sam_segment(self, media_kind: str, media_path, prompt: str, *, on_snapshot: Callable | None = None, include_confidence: bool = True, tag: str = "sam") -> SamResult:
        from meta_sam_parser import CompletedOutcome, image_segmentation_format, video_segmentation_format

        t0 = time.time()
        text = simulate_sam_wire(Path(media_path), prompt, media_kind) if prompt != "road" else ""
        parser = (image_segmentation_format() if media_kind == "image" else video_segmentation_format()).create_parser()
        lines = text.splitlines(keepends=True)
        timeline = []
        for i in range(0, len(lines), 8):
            delta = "".join(lines[i : i + 8])
            timeline.append((round(time.time() - t0, 3), delta))
            for snap in parser.push(delta):
                if on_snapshot:
                    on_snapshot(snap)
            time.sleep(SIM_DELAY)
        fin = parser.finish(CompletedOutcome())
        for snap in fin.events:
            if on_snapshot:
                on_snapshot(snap)
        return SamResult(prompt, media_kind, text, timeline, fin.result, {"simulated": True}, False, time.time() - t0)

    # -- Muse Spark --------------------------------------------------------
    def spark_json(self, messages, schema, *, name="result", model=None, reasoning_effort=None, tag="json") -> dict:
        blob = json.dumps(messages)
        if name == "triage":
            n = sum(1 for m in messages if isinstance(m.get("content"), list) for p in m["content"] if p.get("type") == "image_url")
            return {"frames": [{"index": i, "road_visible": True, "surface_type": "asphalt", "weather": "clear", "lighting": "day", "defect_concepts": ["pothole", "crack"], "notes": "simulated triage"} for i in range(n)], "simulated": True}
        if name == "camera":
            return {"horizon_y_frac": 0.45, "camera_mount": "dashboard", "fisheye": False, "confidence": "low", "notes": "simulated estimate", "simulated": True}
        if name == "crop_judgement":
            out = []
            for did, size in re.findall(r"Defect (D\d{3}):[^;]*; (?:area ([\d.]+))?", blob):
                area = float(size) if size else 0.3
                sev = 2 if area < 0.2 else 3 if area < 0.8 else 4
                out.append({"id": did, "is_defect": True, "depth": "unknown", "edge_condition": "unknown", "severity": sev, "notes": "simulated review (no vision model)"})
            return {"defects": out, "simulated": True}
        if name == "site_rationale":
            ids = sorted(set(re.findall(r"\b(S\d{2})\b", blob)))
            return {"sites": [{"site_id": i, "rationale": f"[simulated] {i} ranks on its worst defect severity, size and nearby exposure (see score factors)."} for i in ids], "simulated": True}
        if name == "tender_sections":
            return {
                "executive_summary": "[simulated text] This RFQ covers repair of the road defects detected in the survey, listed by site in priority order.",
                "scope_of_works": "[simulated text] Repair each defect listed in the Bill of Quantities at the sites shown, highest rank first.",
                "technical_specifications": "[simulated text] Saw-cut patch edges square, remove loose material, apply tack coat, place and compact asphalt; rout, clean and seal cracks.",
                "programme": "[simulated text] Start Rank 1 sites within 14 days of award; complete all sites within 6 weeks.",
                "safety_and_traffic_management": "[simulated text] Provide signage, cones and flaggers at each site during works.",
                "evidence_note": "[simulated text] Each defect has a segmentation mask, an evidence image and a measured size with range.",
                "simulated": True,
            }
        if name == "voice_intent":
            text = blob.lower()
            school = any(w in text for w in ("school", "kids", "children", "pupil"))
            hosp = "hospital" in text or "clinic" in text
            return {"summary": "[simulated] " + (re.search(r'transcript: \\"(.*?)\\"', blob) or [None, ""])[1][:200], "tags": (["school_crossing"] if school else []) + (["near_hospital"] if hosp else []), "near_school": school, "near_hospital": hosp, "near_bus_stop": "bus" in text, "heavy_traffic": "traffic" in text or "truck" in text, "exposure_multiplier": 1.5 if school or hosp else 1.0, "urgency": "high" if school or hosp else "normal", "simulated": True}
        return {"simulated": True}

    def spark_chat(self, messages, *, tools=None, **kwargs) -> dict:
        """Rule-based stand-in for the Ask agent: picks tools by keywords."""
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        had_tools = any(m["role"] == "tool" for m in messages)
        q = str(last_user).lower()
        if tools and not had_tools:
            calls = []
            if "school" in q or "hospital" in q:
                calls.append(("filter_defects", {"near_poi": "school" if "school" in q else "hospital", "within_m": 200}))
            elif "top" in q or "worst" in q or "first" in q:
                calls.append(("top_n", {"n": 5, "by": "priority"}))
            else:
                calls.append(("list_sites", {"limit": 10}))
            return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": f"call_{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]}}]}
        results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        ids = sorted(set(re.findall(r'"(D\d{3}|S\d{2})"', json.dumps(results))))[:12]
        return {"choices": [{"message": {"role": "assistant", "content": f"[simulated answer — no language model] Tool results cover {', '.join(ids) or 'no items'}. See the table below."}}]}

    def transcribe(self, audio_path, **kwargs) -> dict:
        return {"text": "[simulated transcript] Kids cross here every morning on the way to school.", "model": "simulated", "transport": "simulate", "simulated": True}


def provider_name() -> str:
    import os

    from .config import get_settings

    p = os.environ.get("MEND_PROVIDER")
    if p:
        return p
    return "meta" if get_settings().has_key else "simulate"
