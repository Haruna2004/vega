"""Mask helpers: decode SAM payloads, polygons, IoU, drawing."""

from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np


@lru_cache(maxsize=4096)
def _decode(encoding: str, width: int, height: int, payload: str) -> np.ndarray:
    from meta_sam_parser import SegmentationMask, decode_mask_to_raster

    raster = decode_mask_to_raster(SegmentationMask(encoding=encoding, payload=payload, width=width, height=height))
    arr = np.frombuffer(raster, dtype=np.uint8).reshape(height, width)
    arr.setflags(write=False)
    return arr


def decode(m: dict) -> np.ndarray:
    """Decode a stored mask {e,w,h,p} to an (h, w) uint8 0/1 array (box-local)."""
    return _decode(m["e"], int(m["w"]), int(m["h"]), m["p"])


def stored_mask(rec) -> dict:
    mask = rec.mask
    return {"e": mask.encoding, "w": mask.width, "h": mask.height, "p": mask.payload}


def polygons(local: np.ndarray, left: int, top: int, min_area: float = 3.0, eps: float = 0.9) -> list[list[int]]:
    """Outer contours of a box-local mask as flat [x0,y0,x1,y1,...] rings in frame px."""
    if local.size == 0:
        return []
    src = np.ascontiguousarray(local.astype(np.uint8))
    contours, _ = cv2.findContours(src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    rings = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
        if cv2.contourArea(c) < min_area and len(contours) > 1:
            continue
        approx = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        if len(approx) < 3:
            approx = c.reshape(-1, 2)
        approx = approx + np.array([left, top])
        rings.append([int(v) for v in approx.flatten()])
    return rings


def full_mask(det: dict, width: int, height: int) -> np.ndarray:
    out = np.zeros((height, width), dtype=np.uint8)
    l, t, r, b = det["b"]
    local = decode(det["m"])
    h, w = local.shape
    r2, b2 = min(width, l + w), min(height, t + h)
    out[t:b2, l:r2] = local[: b2 - t, : r2 - l]
    return out


def box_iou(a: list[int], b: list[int]) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def mask_iou(a: dict, b: dict) -> float:
    """Exact IoU of two detections (each with box 'b' and stored mask 'm')."""
    if box_iou(a["b"], b["b"]) <= 0:
        return 0.0
    l = min(a["b"][0], b["b"][0])
    t = min(a["b"][1], b["b"][1])
    r = max(a["b"][2], b["b"][2])
    bt = max(a["b"][3], b["b"][3])
    canvas_a = np.zeros((bt - t, r - l), dtype=np.uint8)
    canvas_b = np.zeros_like(canvas_a)
    for det, canvas in ((a, canvas_a), (b, canvas_b)):
        local = decode(det["m"])
        h, w = local.shape
        y0, x0 = det["b"][1] - t, det["b"][0] - l
        canvas[y0 : y0 + h, x0 : x0 + w] = local[: canvas.shape[0] - y0, : canvas.shape[1] - x0]
    inter = np.logical_and(canvas_a, canvas_b).sum()
    union = np.logical_or(canvas_a, canvas_b).sum()
    return float(inter / union) if union else 0.0


def hex_to_bgr(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (b, g, r)


def draw_overlay(img: np.ndarray, rings: list[list[int]], color: str, *, alpha: float = 0.38, thickness: int = 2, glow: bool = True) -> None:
    """Filled translucent mask + crisp outline (+ soft glow) in place (BGR image)."""
    if not rings:
        return
    bgr = hex_to_bgr(color)
    pts = [np.array(r, dtype=np.int32).reshape(-1, 2) for r in rings]
    overlay = img.copy()
    cv2.fillPoly(overlay, pts, bgr, lineType=cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, dst=img)
    if glow:
        glow_layer = np.zeros_like(img)
        cv2.polylines(glow_layer, pts, True, bgr, thickness + 6, cv2.LINE_AA)
        glow_layer = cv2.GaussianBlur(glow_layer, (0, 0), 4)
        cv2.add(img, (glow_layer * 0.6).astype(np.uint8), dst=img)
    cv2.polylines(img, pts, True, bgr, thickness, cv2.LINE_AA)


def draw_label(img: np.ndarray, text: str, x: int, y: int, color: str, *, scale: float = 0.5) -> None:
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), base = cv2.getTextSize(text, font, scale, 1)
    pad = 5
    x = int(max(0, min(img.shape[1] - tw - 2 * pad, x)))
    y = int(max(th + 2 * pad, y))
    bgr = hex_to_bgr(color)
    cv2.rectangle(img, (x, y - th - 2 * pad), (x + tw + 2 * pad, y), (18, 18, 22), -1, cv2.LINE_AA)
    cv2.rectangle(img, (x, y - th - 2 * pad), (x + 3, y), bgr, -1)
    cv2.putText(img, text, (x + pad + 2, y - pad), font, scale, (245, 245, 245), 1, cv2.LINE_AA)
