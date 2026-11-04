"""Stage 4, measure each tracked defect in metres and grade its severity.

Measurement (best available first)
  1. camera_model: pinhole camera over a flat road. Camera height + horizontal FOV
     come from the user's calibration or a mount preset; the horizon row comes
     from the user, else from SAM 3.1's "road" mask apex, else from Muse Spark.
     Mask contours are projected onto the road plane and measured there.
     Uncertainty = spread over camera-parameter perturbations + frame-to-frame spread.
  2. relative: S/M/L/XL bucket from mask area / visible road area (no metres claimed).

Severity = transparent rules (concept, size, wheel path, depth) blended with
Muse Spark's judgement of a 2x crop with SAM's outline drawn on it.
"""

from __future__ import annotations

import itertools
import math
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import Polygon

from ..camera import CAMERA_PRESETS, Camera, polygon_area
from ..config import concept as concept_cfg
from ..config import get_settings
from ..masks import decode, draw_label, draw_overlay
from ..prompts import image_part, render, text_part
from ..store import Run
from . import client

DEFAULT_HORIZON = 0.42
JUDGE_BATCH = 6
MIN_MEASURE_PX = 150  # below this the contour is too coarse for metric measurement
FAR_M = 12.0  # beyond this, perspective makes 1 px span many cm: widen the range


# ----------------------------------------------------------------- calibration
def _road_apex(run: Run, media: dict, frames: list[dict]) -> tuple[float | None, list[dict]]:
    """Horizon from SAM 3.1 'road' masks on a few sampled frames."""
    picks = frames[:: max(1, len(frames) // 4)][:4] if frames else []
    apexes, notes = [], []
    for f in picks:
        try:
            res = client().sam_segment("image", run.dir / f["path"], "road", tag="calibration")
        except Exception as exc:
            notes.append({"frame": f["id"], "error": str(exc)[:200]})
            continue
        best = None
        for rec in res.result.records:
            if getattr(rec, "kind", None) != "mask":
                continue
            from ..masks import stored_mask

            local = decode(stored_mask(rec))
            area = int(local.sum())
            if best is None or area > best[0]:
                best = (area, rec, local)
        if best is None:
            notes.append({"frame": f["id"], "error": "no road mask"})
            continue
        area, rec, local = best
        rows = np.where(local.sum(axis=1) >= max(3, local.shape[1] * 0.004))[0]
        if len(rows) == 0:
            continue
        apex = (rec.bounds.top + rows[0]) / media["height"]
        coverage = area / (media["width"] * media["height"])
        notes.append({"frame": f["id"], "apex_frac": round(float(apex), 4), "road_coverage": round(coverage, 3)})
        if 0.15 < apex < 0.75 and coverage > 0.05:
            apexes.append(float(apex))
    if len(apexes) >= 1:
        return statistics.median(apexes) - 0.01, notes
    return None, notes


def _spark_camera(run: Run, frame: dict) -> dict | None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "horizon_y_frac": {"type": "number"},
            "camera_mount": {"type": "string", "enum": ["dashboard", "handheld", "dashcam_wide", "motorbike", "unknown"]},
            "fisheye": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "notes": {"type": "string"},
        },
        "required": ["horizon_y_frac", "camera_mount", "fisheye", "confidence", "notes"],
    }
    try:
        return client().spark_json(
            [{"role": "system", "content": render("camera")}, {"role": "user", "content": [text_part("Frame:"), image_part(run.dir / frame["path"], max_side=1024)]}],
            schema,
            name="camera",
            reasoning_effort="low",
            tag="camera",
        )
    except Exception as exc:
        run.log(f"Spark camera estimate unavailable: {exc}", level="warn")
        return None


def calibrate(run: Run, media: dict, frames: list[dict], triage: dict | None) -> dict:
    user = run.meta.get("calibration") or {}
    preset_key = user.get("preset") or "phone_dashboard"
    preset = CAMERA_PRESETS.get(preset_key, CAMERA_PRESETS["phone_dashboard"])
    height_m = float(user.get("height_m") or preset["height_m"])
    hfov = float(user.get("hfov_deg") or preset["hfov_deg"])
    road_frames = [f for f in frames if f["media_id"] == media["media_id"]]
    if triage:
        visible = {r["frame_id"] for r in triage.get("frames", []) if r.get("road_visible")}
        road_frames = [f for f in road_frames if f["id"] in visible] or road_frames
    cal = {"media_id": media["media_id"], "preset": preset_key, "height_m": height_m, "hfov_deg": hfov, "user_supplied": bool(user.get("height_m") or user.get("hfov_deg")), "estimates": {}}
    horizon = user.get("horizon_y_frac")
    method = "user"
    spark = _spark_camera(run, road_frames[len(road_frames) // 2]) if road_frames else None
    if spark:
        cal["estimates"]["spark"] = spark
    if horizon is None:
        apex, notes = _road_apex(run, media, road_frames)
        cal["estimates"]["sam_road"] = notes
        if apex is not None:
            horizon, method = apex, "sam_road_apex"
        elif spark and 0.15 < float(spark.get("horizon_y_frac", 0)) < 0.75:
            horizon, method = float(spark["horizon_y_frac"]), "spark_estimate"
        else:
            horizon, method = DEFAULT_HORIZON, "default"
    if spark and not cal["user_supplied"] and spark.get("camera_mount") == "dashcam_wide" and preset_key == "phone_dashboard":
        cal["hfov_deg"] = hfov = CAMERA_PRESETS["dashcam"]["hfov_deg"]
        cal["hfov_note"] = "Muse Spark saw a wide-angle dashcam image; using the dashcam FOV preset"
    cal["horizon_y_frac"] = round(float(horizon), 4)
    cal["horizon_method"] = method
    return cal


def camera_for(media: dict, cal: dict) -> Camera:
    return Camera(media["width"], media["height"], cal["hfov_deg"], cal["height_m"], cal["horizon_y_frac"] * media["height"])


# ------------------------------------------------------------------ geometry
def _largest_ring(poly: list[list[int]]) -> np.ndarray | None:
    best, best_a = None, 0.0
    for ring in poly:
        pts = np.array(ring, dtype=np.float64).reshape(-1, 2)
        if len(pts) < 3:
            continue
        a = polygon_area(pts[:, 0], pts[:, 1])
        if a > best_a:
            best, best_a = pts, a
    return best


def ground_metrics(cam: Camera, poly: list[list[int]]) -> dict | None:
    total, rings = 0.0, []
    for ring in poly:
        pts = np.array(ring, dtype=np.float64).reshape(-1, 2)
        if len(pts) < 3:
            continue
        X, Z = cam.ground_from_pixel(pts[:, 0], pts[:, 1])
        if np.isnan(X).any() or np.isnan(Z).any() or (Z <= 0).any() or (Z > 80).any():
            return None
        total += polygon_area(X, Z)
        rings.append(np.stack([X, Z], axis=1))
    if not rings:
        return None
    main = max(rings, key=lambda r: polygon_area(r[:, 0], r[:, 1]))
    rect = Polygon(main).minimum_rotated_rectangle
    if rect.geom_type == "Polygon":
        xs, zs = rect.exterior.coords.xy
        sides = sorted(math.dist((xs[i], zs[i]), (xs[i + 1], zs[i + 1])) for i in range(2))
    else:  # degenerate (collinear) contour, e.g. a 1-px crack far away
        sides = [0.0, float(getattr(rect, "length", 0.0))]
    cx, cz = float(np.mean(main[:, 0])), float(np.mean(main[:, 1]))
    return {"area_m2": total, "width_m": sides[0], "length_m": sides[1], "lateral_m": cx, "distance_m": cz}


def choose_frames(track: dict, media: dict, cal: dict, k: int = 5) -> tuple[list[dict], bool]:
    W, H = media["width"], media["height"]
    hy = cal["horizon_y_frac"] * H
    ok = [d for d in track["dets"] if d["b"][3] < H - 3 and d["b"][1] > hy + 0.02 * H and d["b"][0] > 2 and d["b"][2] < W - 2]
    partial = False
    if not ok:
        ok = [d for d in track["dets"] if d["b"][1] > hy]
        partial = True
    if not ok:
        return [], True
    ok.sort(key=lambda d: d["a"], reverse=True)
    return ok[:k], partial


def measure_track(track: dict, media: dict, cal: dict) -> dict:
    cam = camera_for(media, cal)
    chosen, partial = choose_frames(track, media, cal)
    qty_kind = concept_cfg(track["concept"]).get("quantity", "area")
    if media["kind"] == "photo" and not chosen:
        chosen, partial = track["dets"], True
    metrics = [(d, ground_metrics(cam, d["poly"])) for d in chosen]
    metrics = [(d, m) for d, m in metrics if m]
    too_small = bool(metrics) and max(d["a"] for d, _ in metrics) < MIN_MEASURE_PX
    if not metrics or too_small:
        best = max(track["dets"], key=lambda d: d["a"])
        below = max(1.0, (1 - cal["horizon_y_frac"]) * media["width"] * media["height"])
        frac = best["a"] / below
        bucket = "S" if frac < 0.002 else "M" if frac < 0.008 else "L" if frac < 0.025 else "XL"
        why = f"only {best['a']} mask pixels at its closest (too far to measure)" if too_small else "mask above horizon or partly out of frame"
        return {"method": "relative", "method_detail": f"{why}; size bucket from mask area / visible road area (no metres claimed)", "size_bucket": bucket, "area_frac": round(frac, 5), "best_frame": best["f"], "best_box": best["b"], "partial": True, "area_m2": None, "width_m": None, "length_m": None, "conf_low": None, "conf_high": None, "lateral_m": None, "distance_m": None}
    best_d, best_m = max(metrics, key=lambda x: x[0]["a"])
    areas = [m["area_m2"] for _, m in metrics]
    # camera-parameter uncertainty on the best frame
    perturbed = []
    for fh, ff, fy in itertools.product((0.85, 1.0, 1.15), (0.9, 1.0, 1.1), (-0.025, 0.0, 0.025)):
        c2 = cam.with_(height_m=cam.height_m * fh, hfov_deg=cam.hfov_deg * ff, horizon_y=cam.horizon_y + fy * cam.height)
        g = ground_metrics(c2, best_d["poly"])
        if g:
            perturbed.append(g)
    key = "length_m" if qty_kind == "length" else "area_m2"
    vals = sorted(p[key] for p in perturbed) or [best_m[key]]
    lo_p, hi_p = vals[max(0, int(0.1 * len(vals)))], vals[min(len(vals) - 1, int(0.9 * len(vals)))]
    frame_vals = sorted(m[key] for _, m in metrics)
    q1, q3 = frame_vals[len(frame_vals) // 4], frame_vals[(3 * len(frame_vals)) // 4]
    central = statistics.median(frame_vals)
    scale = central / best_m[key] if best_m[key] else 1.0
    low, high = min(lo_p * scale, q1), max(hi_p * scale, q3)
    if best_m["distance_m"] > FAR_M:
        low, high = low * 0.75, high * 1.35
    out = {
        "method": "camera_model",
        "method_detail": f"pinhole ground-plane projection; h={cal['height_m']} m, HFOV={cal['hfov_deg']}°, horizon={cal['horizon_y_frac']:.2f}·H ({cal['horizon_method']}); median of {len(metrics)} frames",
        "area_m2": round(statistics.median(areas), 3),
        "width_m": round(statistics.median(m["width_m"] for _, m in metrics), 2),
        "length_m": round(statistics.median(m["length_m"] for _, m in metrics), 2),
        "quantity_key": key,
        "conf_low": round(low, 3),
        "conf_high": round(high, 3),
        "lateral_m": round(best_m["lateral_m"], 2),
        "distance_m": round(best_m["distance_m"], 1),
        "best_frame": best_d["f"],
        "best_box": best_d["b"],
        "frames_used": [d["f"] for d, _ in metrics],
        "partial": partial,
    }
    if partial:
        out["method_detail"] += "; defect partly out of frame, size is a lower bound"
    return out


def position_class(lateral_m: float | None) -> str:
    if lateral_m is None:
        return "unknown"
    a = abs(lateral_m)
    if a < 0.35:
        return "centre"
    if a <= 1.35:
        return "wheel_path"
    return "edge"


def rule_severity(concept_id: str, m: dict, position: str, depth: str | None) -> tuple[int, list[str]]:
    c = concept_cfg(concept_id)
    sev = c.get("base_severity", 2)
    why = [f"base {sev} for {c['label'].lower()}"]
    area, length = m.get("area_m2"), m.get("length_m")
    if concept_id == "pothole" and area is not None:
        if area < 0.1:
            sev -= 1
            why.append("small (<0.1 m²) −1")
        elif area >= 1.5:
            sev += 2
            why.append("very large (≥1.5 m²) +2")
        elif area >= 0.5:
            sev += 1
            why.append("large (≥0.5 m²) +1")
    elif concept_id in ("alligator_crack", "rutting") and area is not None:
        if area >= 6:
            sev += 2
            why.append("extensive (≥6 m²) +2")
        elif area >= 2:
            sev += 1
            why.append("wide area (≥2 m²) +1")
    elif concept_id in ("crack", "longitudinal_crack", "transverse_crack", "edge_break") and length is not None:
        if length >= 10:
            sev += 2
            why.append("long (≥10 m) +2")
        elif length >= 3:
            sev += 1
            why.append("long (≥3 m) +1")
    elif concept_id == "standing_water" and area is not None and area >= 3:
        sev += 1
        why.append("large ponding (≥3 m²) +1")
    if m.get("size_bucket") in ("L", "XL"):
        sev += 1
        why.append(f"relative size {m['size_bucket']} +1")
    if position == "wheel_path" and concept_id in ("pothole", "crack", "longitudinal_crack", "transverse_crack", "alligator_crack", "rutting", "edge_break", "missing_manhole_cover"):
        sev += 1
        why.append("in wheel path +1")
    if depth == "deep":
        sev += 1
        why.append("deep (Spark review) +1")
    elif depth == "shallow":
        sev -= 1
        why.append("shallow (Spark review) −1")
    return max(1, min(5, sev)), why


# ------------------------------------------------------------------ evidence
def grab_frames(run: Run, media: dict, wanted: set[int]) -> dict[int, np.ndarray]:
    if media["kind"] == "photo":
        return {0: cv2.imread(str(run.dir / media["proxy"]))}
    cap = cv2.VideoCapture(str(run.dir / media["proxy"]))
    out: dict[int, np.ndarray] = {}
    idx, last = 0, max(wanted) if wanted else -1
    while idx <= last:
        ok, img = cap.read()
        if not ok:
            break
        if idx in wanted:
            out[idx] = img
        idx += 1
    cap.release()
    return out


def write_evidence(run: Run, defect: dict, track: dict, frame_img: np.ndarray) -> None:
    det = next(d for d in track["dets"] if d["f"] == defect["best_frame"])
    color = track["color"]
    full = frame_img.copy()
    draw_overlay(full, det["poly"], color, alpha=0.35, thickness=3)
    size = f" {defect['area_m2']:.2f} m2" if defect.get("area_m2") else (f" size {defect.get('size_bucket')}" if defect.get("size_bucket") else "")
    draw_label(full, f"{defect['id']} {track['label'].upper()}{size}", det["b"][0], det["b"][1] - 6, color, scale=0.6)
    cv2.imwrite(str(run.dir / "evidence" / f"{defect['id']}_frame.jpg"), full, [cv2.IMWRITE_JPEG_QUALITY, 88])
    # 2x zoom crop with outline only
    l, t, r, b = det["b"]
    pad = int(max(r - l, b - t) * 0.6) + 24
    H, W = frame_img.shape[:2]
    x0, y0, x1, y1 = max(0, l - pad), max(0, t - pad), min(W, r + pad), min(H, b + pad)
    crop = frame_img[y0:y1, x0:x1].copy()
    shifted = [[v - (x0 if i % 2 == 0 else y0) for i, v in enumerate(ring)] for ring in det["poly"]]
    draw_overlay(crop, shifted, color, alpha=0.12, thickness=1, glow=False)
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(str(run.dir / "evidence" / f"{defect['id']}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    raw = frame_img[y0:y1, x0:x1]
    cv2.imwrite(str(run.dir / "evidence" / f"{defect['id']}_raw.jpg"), cv2.resize(raw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), [cv2.IMWRITE_JPEG_QUALITY, 90])
    defect["evidence"] = f"evidence/{defect['id']}.jpg"
    defect["evidence_frame"] = f"evidence/{defect['id']}_frame.jpg"
    defect["evidence_raw"] = f"evidence/{defect['id']}_raw.jpg"


# ------------------------------------------------------------------ Spark review
def judge_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "defects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "is_defect": {"type": "boolean"},
                        "depth": {"type": "string", "enum": ["shallow", "moderate", "deep", "unknown"]},
                        "edge_condition": {"type": "string", "enum": ["clean", "ragged", "crumbling", "unknown"]},
                        "severity": {"type": "integer"},
                        "notes": {"type": "string"},
                    },
                    "required": ["id", "is_defect", "depth", "edge_condition", "severity", "notes"],
                },
            }
        },
        "required": ["defects"],
    }


def _size_text(d: dict) -> str:
    if d.get("area_m2") is not None:
        return f"area {d['area_m2']:.2f} m² (range {d['conf_low']:.2f}–{d['conf_high']:.2f} for {d.get('quantity_key', 'area_m2').replace('_m2', ' m²').replace('_m', ' m')}), length {d['length_m']:.2f} m, width {d['width_m']:.2f} m, lateral offset {d['lateral_m']:+.1f} m ({d['position'].replace('_', ' ')})"
    return f"relative size {d.get('size_bucket')} (no metric measurement)"


def judge_batch(run: Run, batch: list[dict]) -> dict[str, dict]:
    content: list[dict] = [text_part(f"{len(batch)} detections follow.")]
    for d in batch:
        content.append(text_part(f"Defect {d['id']}: SAM concept '{d['label']}', SAM confidence {d.get('conf')}, seen in {d['n_frames']} frames; {_size_text(d)}."))
        content.append(image_part(run.dir / d["evidence"], max_side=640))
    out = client().spark_json([{"role": "system", "content": render("crop_judge")}, {"role": "user", "content": content}], judge_schema(), name="crop_judgement", reasoning_effort="low", tag="crop_judge")
    return {r["id"]: r for r in out.get("defects", []) if r.get("id")}


# ------------------------------------------------------------------ stage
def measure(run: Run) -> dict:
    run.set_stage("measure", "running")
    media = run.read("media")
    frames = run.read("frames")
    triage = run.read("triage")
    tracks = run.read("detections")["tracks"]
    calibrations = {}
    for m in media:
        if not any(t["media_id"] == m["media_id"] for t in tracks):
            continue
        cal = calibrate(run, m, frames, triage)
        calibrations[m["media_id"]] = cal
        run.emit("calibration", **cal)
    run.write("calibration", calibrations)

    defects: list[dict] = []
    by_media: dict[str, list[dict]] = defaultdict(list)
    for i, t in enumerate(tracks, 1):
        m = next(mm for mm in media if mm["media_id"] == t["media_id"])
        cal = calibrations[m["media_id"]]
        meas = measure_track(t, m, cal)
        position = position_class(meas.get("lateral_m"))
        d = {
            "id": f"D{i:03d}",
            "track_id": t["id"],
            "media_id": t["media_id"],
            "concept": t["concept"],
            "label": t["label"],
            "color": t["color"],
            "prompt": t["prompt"],
            "first": t["first"],
            "last": t["last"],
            "n_frames": t["n"],
            "conf": t["conf"],
            "merged_from": t.get("merged_from", []),
            "t": round(meas["best_frame"] / m["fps"], 2) if m.get("fps") else 0.0,
            "position": position,
            **meas,
        }
        defects.append(d)
        by_media[m["media_id"]].append(d)

    # evidence crops (one sequential decode per video)
    tracks_by_id = {t["id"]: t for t in tracks}
    for mid, ds in by_media.items():
        m = next(mm for mm in media if mm["media_id"] == mid)
        imgs = grab_frames(run, m, {d["best_frame"] for d in ds})
        for d in ds:
            if d["best_frame"] in imgs:
                write_evidence(run, d, tracks_by_id[d["track_id"]], imgs[d["best_frame"]])

    # Muse Spark review of every crop, batched
    reviews: dict[str, dict] = {}
    with_evidence = [d for d in defects if d.get("evidence")]
    batches = [with_evidence[i : i + JUDGE_BATCH] for i in range(0, len(with_evidence), JUDGE_BATCH)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for res in pool.map(lambda b: _safe_judge(run, b), batches):
            reviews.update(res)

    for d in defects:
        r = reviews.get(d["id"])
        depth = r.get("depth") if r else None
        sev_rule, why = rule_severity(d["concept"], d, d["position"], depth if depth != "unknown" else None)
        d["severity_rule"] = sev_rule
        d["severity_factors"] = why
        if r:
            spark_sev = max(1, min(5, int(r.get("severity") or sev_rule)))
            d["review"] = r
            d["severity_spark"] = spark_sev
            d["severity"] = int(round((sev_rule + spark_sev) / 2 + 0.01))
            d["dismissed"] = not r.get("is_defect", True)
        else:
            d["severity"] = sev_rule
            d["dismissed"] = False
        run.emit("defect", defect={k: d.get(k) for k in ("id", "track_id", "media_id", "concept", "label", "color", "severity", "area_m2", "length_m", "quantity_key", "conf_low", "conf_high", "method", "size_bucket", "position", "evidence", "t", "best_frame", "dismissed")})

    run.write("defects", defects)
    from .segment import write_overlays

    extra = {d["track_id"]: {"defect_id": d["id"], "severity": d["severity"], "area_m2": d.get("area_m2"), "dismissed": d["dismissed"]} for d in defects}
    write_overlays(run, media, tracks, extra)
    kept = [d for d in defects if not d["dismissed"]]
    run.set_stage("measure", "done", defects=len(defects), dismissed=len(defects) - len(kept), area_m2=round(sum(d.get("area_m2") or 0 for d in kept), 2), reviewed=len(reviews))
    return {"defects": defects, "calibration": calibrations}


def _safe_judge(run: Run, batch: list[dict]) -> dict[str, dict]:
    try:
        return judge_batch(run, batch)
    except Exception as exc:
        run.log(f"Spark crop review unavailable for {', '.join(d['id'] for d in batch)}: {exc}", level="warn")
        return {}


def evidence_path(run: Run, defect_id: str) -> Path:
    return run.dir / "evidence" / f"{defect_id}.jpg"
