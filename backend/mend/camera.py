"""Pinhole camera over a flat road: pixel <-> ground-plane metres.

World frame: X right, Y down, Z forward (horizontal). Camera at the origin,
pitched down by theta, road plane at Y = height_m. The horizon row fixes theta:
    horizon_y = cy - f * tan(theta)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class Camera:
    width: int
    height: int
    hfov_deg: float
    height_m: float
    horizon_y: float  # pixel row of the horizon (may be above the frame)
    roll_deg: float = 0.0

    @property
    def f(self) -> float:
        return (self.width / 2) / math.tan(math.radians(self.hfov_deg) / 2)

    @property
    def cx(self) -> float:
        return self.width / 2

    @property
    def cy(self) -> float:
        return self.height / 2

    @property
    def pitch(self) -> float:
        return math.atan((self.cy - self.horizon_y) / self.f)

    def with_(self, **changes) -> "Camera":
        return replace(self, **changes)

    def ground_from_pixel(self, u, v):
        """Pixel(s) -> (X, Z) metres on the road. NaN at/above the horizon."""
        u = np.asarray(u, dtype=np.float64)
        v = np.asarray(v, dtype=np.float64)
        th = self.pitch
        xc = (u - self.cx) / self.f
        yc = (v - self.cy) / self.f
        denom = yc * math.cos(th) + math.sin(th)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(denom > 1e-6, self.height_m / denom, np.nan)
        X = t * xc
        Z = t * (math.cos(th) - yc * math.sin(th))
        return X, Z

    def pixel_from_ground(self, X, Z):
        X = np.asarray(X, dtype=np.float64)
        Z = np.asarray(Z, dtype=np.float64)
        th = self.pitch
        yc = self.height_m * math.cos(th) - Z * math.sin(th)
        zc = self.height_m * math.sin(th) + Z * math.cos(th)
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.cx + self.f * X / zc
            v = self.cy + self.f * yc / zc
        return u, v

    def ground_scale_at_row(self, v: float) -> float:
        """Metres per pixel (lateral) at image row v."""
        X0, _ = self.ground_from_pixel(self.cx, v)
        X1, _ = self.ground_from_pixel(self.cx + 1, v)
        return float(abs(X1 - X0))


def polygon_area(xs: np.ndarray, ys: np.ndarray) -> float:
    return float(abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1))) / 2)


# Presets for the New Run screen. Heights are camera lens heights above the road.
CAMERA_PRESETS = {
    "phone_dashboard": {"label": "Phone on dashboard / windscreen", "height_m": 1.25, "hfov_deg": 68.0},
    "phone_handheld": {"label": "Phone held by passenger", "height_m": 1.2, "hfov_deg": 68.0},
    "dashcam": {"label": "Dashcam (wide angle)", "height_m": 1.3, "hfov_deg": 110.0},
    "action_cam": {"label": "Action camera (GoPro-style, linear mode)", "height_m": 1.4, "hfov_deg": 92.0},
    "motorbike": {"label": "Phone on motorbike / bicycle handlebar", "height_m": 1.0, "hfov_deg": 68.0},
}
