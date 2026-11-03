"""Stage 6 — rank sites: priority = severity score x exposure.

severity score: worst defect severity plus a share of the others (a site with one
severity-5 pothole and three cracks outranks a lone severity-5 pothole).
exposure: road class x vulnerable-user POIs within 150 m x defect density
x voice-note multiplier. Muse Spark explains the top 10 citing these numbers.
"""

from __future__ import annotations

from ..prompts import render
from ..store import Run
from . import client
from .geo import POI_RADIUS_M, ROAD_CLASS_WEIGHT

POI_BONUS = {"school": 0.5, "hospital": 0.35, "bus_stop": 0.2, "market": 0.2, "place_of_worship": 0.1}
TOP_N_RATIONALE = 10


def site_scores(site: dict, defects: dict[str, dict], voice: dict | None) -> dict:
    sev = sorted((defects[i]["severity"] for i in site["defect_ids"] if i in defects), reverse=True)
    if not sev:
        return {"severity_score": 0, "exposure": 0, "priority_score": 0, "factors": []}
    severity_score = sev[0] + 0.35 * sum(sev[1:])
    severity_score = min(severity_score, 8.0)
    factors = [f"worst severity {sev[0]}" + (f" + {len(sev) - 1} more defects" if len(sev) > 1 else "")]
    road_w = ROAD_CLASS_WEIGHT.get(site.get("road_class") or "unknown", 0.6)
    factors.append(f"road class {site.get('road_class') or 'unknown'} ×{road_w:.2f}")
    poi_mult = 1.0
    kinds = {}
    for p in site.get("pois", []):
        if p["kind"] in POI_BONUS and p["kind"] not in kinds and p["distance_m"] <= POI_RADIUS_M:
            kinds[p["kind"]] = p
    for k, p in kinds.items():
        poi_mult += POI_BONUS[k]
        factors.append(f"{p['name']} ({k.replace('_', ' ')}) {p['distance_m']} m away +{POI_BONUS[k]:.2f}")
    density = 1.0 + 0.08 * (len(sev) - 1)
    voice_mult = 1.0
    if voice:
        intent = voice.get("intent") or {}
        voice_mult = float(intent.get("exposure_multiplier") or 1.0)
        voice_mult = max(0.5, min(2.0, voice_mult))
        for flag, k in (("near_school", "school"), ("near_hospital", "hospital"), ("near_bus_stop", "bus_stop")):
            if intent.get(flag) and k not in kinds:
                poi_mult += POI_BONUS[k]
                factors.append(f"field note: near {k.replace('_', ' ')} +{POI_BONUS[k]:.2f}")
        if voice_mult != 1.0:
            factors.append(f"field note exposure ×{voice_mult:.2f}")
    exposure = road_w * poi_mult * density * voice_mult
    raw = severity_score * exposure
    return {"severity_score": round(severity_score, 2), "exposure": round(exposure, 3), "raw": raw, "factors": factors}


def rationale_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"sites": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"site_id": {"type": "string"}, "rationale": {"type": "string"}}, "required": ["site_id", "rationale"]}}},
        "required": ["sites"],
    }


def site_brief(site: dict, defects: dict[str, dict]) -> dict:
    ds = [defects[i] for i in site["defect_ids"] if i in defects]
    return {
        "site_id": site["id"],
        "rank": site.get("rank"),
        "priority_score": site.get("priority_score"),
        "street": site.get("street"),
        "road_class": site.get("road_class"),
        "nearby": [f"{p['name']} ({p['kind']}, {p['distance_m']} m)" for p in site.get("pois", [])[:4]],
        "field_note": (site.get("voice") or {}).get("transcript"),
        "score_factors": site.get("factors"),
        "defects": [
            {
                "id": d["id"],
                "type": d["label"],
                "severity": d["severity"],
                "size": (f"{d['area_m2']:.2f} m² (range {d['conf_low']:.2f}–{d['conf_high']:.2f})" if d.get("area_m2") is not None and d.get("quantity_key") != "length_m" else f"{d['length_m']:.1f} m long" if d.get("length_m") else f"relative size {d.get('size_bucket')}"),
                "position": d.get("position"),
                "review": (d.get("review") or {}).get("notes"),
            }
            for d in ds
        ],
    }


def write_rationales(run: Run, sites: list[dict], defects: dict[str, dict]) -> None:
    top = [s for s in sites if s.get("rank") and s["rank"] <= TOP_N_RATIONALE]
    if not top:
        return
    try:
        import json

        out = client().spark_json(
            [{"role": "system", "content": render("rationale")}, {"role": "user", "content": "Sites (ranked):\n" + json.dumps([site_brief(s, defects) for s in top], ensure_ascii=False, indent=1)}],
            rationale_schema(),
            name="site_rationale",
            reasoning_effort="low",
            tag="rationale",
        )
        by_id = {r["site_id"]: r["rationale"] for r in out.get("sites", [])}
        for s in top:
            if s["id"] in by_id:
                s["rationale"] = by_id[s["id"]]
                s["rationale_by"] = "muse-spark"
    except Exception as exc:
        run.log(f"Spark rationale unavailable: {exc}", level="warn")
    for s in top:
        if not s.get("rationale"):
            s["rationale"] = "; ".join(s.get("factors", []))
            s["rationale_by"] = "rules"


def rank(sites: list[dict], defects: dict[str, dict]) -> None:
    for s in sites:
        sc = site_scores(s, defects, s.get("voice"))
        s.update({k: sc[k] for k in ("severity_score", "exposure", "factors")})
        s["_raw"] = sc.get("raw", 0)
    top = max((s["_raw"] for s in sites), default=0) or 1
    for s in sites:
        # 0-100 scale against the theoretical max (severity 8 x exposure ~2.2)
        s["priority_score"] = round(min(100.0, 100 * s.pop("_raw") / (8 * 2.2)), 1)
    for r, s in enumerate(sorted(sites, key=lambda s: -s["priority_score"]), 1):
        s["rank"] = r


def prioritize(run: Run, *, with_rationale: bool = True) -> dict:
    run.set_stage("prioritize", "running")
    sites = run.read("sites", [])
    defects = {d["id"]: d for d in run.read("defects", [])}
    old = {s["id"]: s.get("rank") for s in sites}
    rank(sites, defects)
    if with_rationale:
        for s in sites:
            s.pop("rationale", None)
        write_rationales(run, sites, defects)
    sites.sort(key=lambda s: s["rank"])
    run.write("sites", sites)
    for s in sites:
        run.emit("rank", site_id=s["id"], rank=s["rank"], priority_score=s["priority_score"], previous_rank=old.get(s["id"]))
    run.set_stage("prioritize", "done", sites=len(sites), top=[s["id"] for s in sites[:3]])
    return {"sites": sites}
