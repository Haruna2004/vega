"""Field voice notes: Muse Voice Transcribe -> Muse Spark intent -> re-rank.

"Kids cross here every morning" becomes {near_school: true, exposure x1.5, tags:
[school_crossing]} on that site, the site's exposure goes up, and the ranking,
work order and tender are regenerated.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from ..prompts import render
from ..store import Run
from . import client


def intent_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "near_school": {"type": "boolean"},
            "near_hospital": {"type": "boolean"},
            "near_bus_stop": {"type": "boolean"},
            "heavy_traffic": {"type": "boolean"},
            "exposure_multiplier": {"type": "number"},
            "urgency": {"type": "string", "enum": ["low", "normal", "high", "immediate"]},
        },
        "required": ["summary", "tags", "near_school", "near_hospital", "near_bus_stop", "heavy_traffic", "exposure_multiplier", "urgency"],
    }


def extract_intent(run: Run, transcript: str, site: dict | None, defects: list[dict]) -> dict:
    ctx = {
        "site": {k: (site or {}).get(k) for k in ("id", "street", "road_class")} if site else None,
        "nearby_osm": [p["name"] + f" ({p['kind']}, {p['distance_m']} m)" for p in (site or {}).get("pois", [])[:4]],
        "defects": [{"id": d["id"], "type": d["label"], "severity": d["severity"]} for d in defects],
    }
    return client().spark_json(
        [{"role": "system", "content": render("voice_intent")}, {"role": "user", "content": f"Voice note transcript: \"{transcript}\"\nContext: {json.dumps(ctx, ensure_ascii=False)}"}],
        intent_schema(),
        name="voice_intent",
        reasoning_effort="low",
        tag="voice_intent",
    )


def add_voice_note(run: Run, target_kind: str, target_id: str, audio_path: Path | None, *, rebuild_docs: bool = True, typed_text: str | None = None) -> dict:
    from .prioritize import prioritize
    from .report import build_documents

    sites = run.read("sites", [])
    defects = {d["id"]: d for d in run.read("defects", [])}
    if target_kind == "defect":
        site_id = defects[target_id].get("site_id")
    else:
        site_id = target_id
    site = next((s for s in sites if s["id"] == site_id), None)
    note_id = f"V{int(time.time() * 1000) % 10_000_000:07d}"
    t0 = time.time()
    dst = None
    if audio_path is not None:
        dst = run.dir / "voice" / f"{note_id}{audio_path.suffix or '.webm'}"
        dst.parent.mkdir(exist_ok=True)
        shutil.copy2(audio_path, dst)
    if typed_text:
        tr = {"text": typed_text, "model": "typed by inspector", "transport": "keyboard"}
    else:
        tr = client().transcribe(dst, keywords=["pothole", "school", "crossing", "hospital", "bus stop"])
    transcript = (tr.get("text") or "").strip()
    intent = extract_intent(run, transcript, site, [defects[i] for i in (site or {}).get("defect_ids", []) if i in defects]) if transcript else {}
    note = {
        "id": note_id,
        "target_kind": target_kind,
        "target_id": target_id,
        "site_id": site_id,
        "audio": run.rel(dst) if dst else None,
        "transcript": transcript,
        "model": tr.get("model"),
        "transport": tr.get("transport"),
        "intent": intent,
        "created_at": time.time(),
        "latency_s": round(time.time() - t0, 2),
    }
    notes = run.read("voice_notes", [])
    notes.append(note)
    run.write("voice_notes", notes)
    old_rank = site.get("rank") if site else None
    if site:
        site["voice"] = {"id": note_id, "transcript": transcript, "model": tr.get("model"), "intent": intent, "audio": note["audio"]}
        if target_kind == "defect" and target_id in defects:
            d = defects[target_id]
            d.setdefault("notes", []).append({"voice_id": note_id, "transcript": transcript})
            run.write("defects", list(defects.values()))
        run.write("sites", sites)
        prioritize(run, with_rationale=True)
        if rebuild_docs:
            build_documents(run, pdf=True)
    sites = run.read("sites", [])
    new = next((s for s in sites if s["id"] == site_id), None)
    run.emit("voice_note", note=note, old_rank=old_rank, new_rank=(new or {}).get("rank"))
    return {"note": note, "site_id": site_id, "old_rank": old_rank, "new_rank": (new or {}).get("rank"), "site": new}
