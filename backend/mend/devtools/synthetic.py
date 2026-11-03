"""Synthetic road scene for tests (NOT used in the demo).

Renders a drive over a flat road with the same pinhole model the measure stage
uses, with potholes / cracks / puddles of KNOWN size placed on the ground. Gives
us (1) a video to run the pipeline on without real footage or API credits and
(2) ground truth to check the measurement maths against.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..camera import Camera


@dataclass
class Defect:
    concept: str
    x: float  # lateral centre (m), + right
    z: float  # distance along the road from the start (m)
    a: float  # semi-axis across (m)
    b: float  # semi-axis along (m)
    kind: str = "ellipse"  # ellipse | crack
    angle: float = 0.0
    shade: float = 0.25

    @property
    def area_m2(self) -> float:
        return math.pi * self.a * self.b if self.kind == "ellipse" else 0.0


@dataclass
class Scene:
    width: int = 1280
    height: int = 720
    fps: float = 15.0
    seconds: float = 8.0
    speed_mps: float = 7.0
    camera_height_m: float = 1.3
    hfov_deg: float = 70.0
    horizon_frac: float = 0.40
    road_half_width: float = 3.6
    defects: list[Defect] = field(default_factory=list)
    seed: int = 7

    @property
    def camera(self) -> Camera:
        return Camera(self.width, self.height, self.hfov_deg, self.camera_height_m, self.horizon_frac * self.height)

    @property
    def n_frames(self) -> int:
        return int(round(self.seconds * self.fps))

    def z_offset(self, frame: int) -> float:
        return self.speed_mps * frame / self.fps


def default_scene() -> Scene:
    return Scene(
        defects=[
            Defect("pothole", x=0.9, z=14.0, a=0.45, b=0.35),
            Defect("pothole", x=-1.1, z=26.0, a=0.7, b=0.5),
            Defect("standing_water", x=2.6, z=36.0, a=0.8, b=1.4, shade=0.55),
            Defect("crack", x=-0.4, z=44.0, a=0.03, b=2.2, kind="crack", angle=0.3),
            Defect("pothole", x=0.3, z=55.0, a=0.35, b=0.3),
            Defect("pothole", x=0.55, z=56.5, a=0.25, b=0.2),
        ]
    )


def _masks_for(scene: Scene, X: np.ndarray, Z: np.ndarray) -> list[np.ndarray]:
    out = []
    for d in scene.defects:
        dx = X - d.x
        dz = Z - d.z
        if d.kind == "crack":
            c, s = math.cos(d.angle), math.sin(d.angle)
            along = dx * s + dz * c
            across = dx * c - dz * s
            wiggle = 0.05 * np.sin(along * 7.0)
            m = (np.abs(along) < d.b) & (np.abs(across - wiggle) < d.a)
        else:
            m = (dx / d.a) ** 2 + (dz / d.b) ** 2 < 1.0
        out.append(np.nan_to_num(m, nan=False).astype(bool))
    return out


def render_frame(scene: Scene, frame: int, rays: tuple[np.ndarray, np.ndarray], rng: np.random.Generator) -> tuple[np.ndarray, list[np.ndarray]]:
    Xg, Zg = rays
    Z = Zg + scene.z_offset(frame)
    X = Xg
    h, w = scene.height, scene.width
    img = np.zeros((h, w, 3), dtype=np.float32)
    ground = ~np.isnan(Zg)
    # sky gradient
    rows = np.linspace(0, 1, h)[:, None]
    sky = np.stack([0.55 + 0.25 * rows, 0.62 + 0.2 * rows, 0.75 + 0.1 * rows], axis=-1) * np.ones((1, w, 1))
    img[:] = sky
    road = ground & (np.abs(X) < scene.road_half_width)
    shoulder = ground & ~road
    tex = 0.36 + 0.05 * np.sin(Z * 13.1 + X * 7.7) * np.cos(Z * 3.3 - X * 11.0)
    noise = rng.normal(0, 0.025, size=(h, w)).astype(np.float32)
    img[road] = np.stack([tex, tex, tex * 1.02], axis=-1)[road] + noise[road, None]
    img[shoulder] = np.stack([0.33 + 0.0 * X, 0.42 + 0.03 * np.sin(Z * 5), 0.22 + 0.0 * X], axis=-1)[shoulder]
    # lane markings: edges + dashed centre
    edge = road & (np.abs(np.abs(X) - (scene.road_half_width - 0.15)) < 0.07)
    centre = road & (np.abs(X) < 0.06) & ((Z % 6.0) < 3.0)
    img[edge | centre] = 0.9
    masks = _masks_for(scene, X, Z)
    for d, m in zip(scene.defects, masks):
        if d.concept == "standing_water":
            img[m] = img[m] * 0.4 + np.array([0.35, 0.42, 0.5]) * 0.6
        else:
            img[m] = d.shade + 0.04 * np.sin(Z[m, None] * 40)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8), masks


def render_video(scene: Scene, out: Path) -> Path:
    cam = scene.camera
    vv, uu = np.mgrid[0 : scene.height, 0 : scene.width]
    rays = cam.ground_from_pixel(uu + 0.5, vv + 0.5)
    rng = np.random.default_rng(scene.seed)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{scene.width}x{scene.height}", "-r", str(scene.fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)],
        stdin=subprocess.PIPE,
    )
    for n in range(scene.n_frames):
        img, _ = render_frame(scene, n, rays, rng)
        assert proc.stdin is not None
        proc.stdin.write(img.tobytes())
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait()
    return out


def frame_masks(scene: Scene, frame: int, rays) -> list[np.ndarray]:
    Xg, Zg = rays
    return _masks_for(scene, Xg, Zg + scene.z_offset(frame))


def encode_record(obj_id: int, mask: np.ndarray, conf: float) -> str | None:
    from meta_sam_parser import _mask_codec  # private encoder, tests only

    ys, xs = np.nonzero(mask)
    if len(xs) < 6:
        return None
    x1, x2, y1, y2 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    crop = mask[y1 : y2 + 1, x1 : x2 + 1].astype(np.uint8)
    hh, ww = crop.shape
    payload = _mask_codec._encode_raster(crop.flatten().tolist(), ww, hh)
    h, w = mask.shape
    return f"{obj_id}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h};c={conf:.3f}|><|mask;x=0;y=0;data={hh},{ww},{payload}|>"


def sam_wire_text(scene: Scene, prompt_concepts: set[str], start: int, end: int) -> str:
    """SAM 3.1 wire text for frames [start, end) of the scene (frame ids local)."""
    cam = scene.camera
    vv, uu = np.mgrid[0 : scene.height, 0 : scene.width]
    rays = cam.ground_from_pixel(uu + 0.5, vv + 0.5)
    lines = []
    ids = {i: 3 + 2 * i for i in range(len(scene.defects))}  # non-dense ids, like the API
    for n in range(start, end):
        masks = frame_masks(scene, n, rays)
        recs = []
        for i, (d, m) in enumerate(zip(scene.defects, masks)):
            if d.concept not in prompt_concepts:
                continue
            rec = encode_record(ids[i], m, 0.82 + 0.1 * math.sin(n * 0.3 + i))
            if rec:
                recs.append(rec)
        if recs:
            lines.append(f"<{n - start}f>" + ",".join(recs))
    return "\n".join(lines) + ("\n" if lines else "")
