"""GPS sources (video metadata, EXIF, GPX, CSV, drawn route) and interpolation."""

from __future__ import annotations

import csv
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EARTH_R = 6371008.8

_ISO6709 = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def offset_point(lat: float, lon: float, bearing: float, dist_m: float) -> tuple[float, float]:
    """Move `dist_m` metres from (lat, lon) along `bearing` degrees."""
    d = dist_m / EARTH_R
    b = math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def parse_iso6709(text: str | None) -> tuple[float, float] | None:
    if not text:
        return None
    m = _ISO6709.search(text)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0):
        return None
    return lat, lon


def video_location(probe: dict) -> tuple[float, float] | None:
    tags: dict[str, Any] = {}
    tags.update((probe.get("format") or {}).get("tags") or {})
    for st in probe.get("streams") or []:
        tags.update(st.get("tags") or {})
    for key in ("location", "com.apple.quicktime.location.ISO6709", "location-eng"):
        loc = parse_iso6709(tags.get(key))
        if loc:
            return loc
    return None


def parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def exif_gps(path: Path) -> tuple[float, float] | None:
    try:
        from PIL import Image
        from PIL.ExifTags import GPSTAGS

        with Image.open(path) as im:
            exif = im.getexif()
            gps_ifd = exif.get_ifd(0x8825)
            if not gps_ifd:
                return None
            gps = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}

        def to_deg(vals, ref):
            d, m, s = (float(v) for v in vals)
            deg = d + m / 60 + s / 3600
            return -deg if ref in ("S", "W") else deg

        lat = to_deg(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
        lon = to_deg(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
        if lat == 0 and lon == 0:
            return None
        return lat, lon
    except Exception:
        return None


def exif_time(path: Path) -> datetime | None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            exif = im.getexif()
            sub = exif.get_ifd(0x8769)
            raw = sub.get(36867) or exif.get(306)
        if raw:
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def read_gpx(path: Path) -> list[dict]:
    import gpxpy

    gpx = gpxpy.parse(path.read_text())
    pts = []
    for trk in gpx.tracks:
        for seg in trk.segments:
            for p in seg.points:
                pts.append({"lat": p.latitude, "lon": p.longitude, "time": p.time.isoformat() if p.time else None})
    if not pts:
        for rte in gpx.routes:
            for p in rte.points:
                pts.append({"lat": p.latitude, "lon": p.longitude, "time": p.time.isoformat() if p.time else None})
    return pts


def read_csv_route(path: Path) -> list[dict]:
    pts = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            low = {k.strip().lower(): v for k, v in row.items() if k}
            lat = low.get("lat") or low.get("latitude")
            lon = low.get("lon") or low.get("lng") or low.get("longitude")
            if lat is None or lon is None:
                continue
            pt = {"lat": float(lat), "lon": float(lon), "time": low.get("time") or low.get("timestamp")}
            if low.get("t") or low.get("t_s"):
                pt["t"] = float(low.get("t") or low.get("t_s"))
            pts.append(pt)
    return pts


def route_points_for_media(points: list[dict], duration_s: float, start_time: datetime | None) -> list[dict]:
    """Map a GPS track onto media time (seconds). Uses timestamps when they overlap
    the video, otherwise spreads the track evenly over the clip duration."""
    if not points:
        return []
    if all("t" in p for p in points):
        return [{"t": float(p["t"]), "lat": p["lat"], "lon": p["lon"]} for p in points]
    times = [parse_time(p.get("time")) for p in points]
    if start_time and all(times):
        rel = [(t - start_time).total_seconds() for t in times]  # type: ignore[operator]
        if rel[0] <= duration_s and rel[-1] >= 0:
            return [{"t": r, "lat": p["lat"], "lon": p["lon"]} for r, p in zip(rel, points)]
    return polyline_over_time(points, duration_s)


def polyline_over_time(points: list[dict], duration_s: float) -> list[dict]:
    """Constant-speed interpolation along a polyline (used for drawn routes)."""
    if len(points) == 1:
        return [{"t": 0.0, "lat": points[0]["lat"], "lon": points[0]["lon"]}]
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        cum.append(cum[-1] + haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]))
    total = cum[-1] or 1.0
    return [{"t": duration_s * c / total, "lat": p["lat"], "lon": p["lon"]} for c, p in zip(cum, points)]


def interpolate(route: list[dict], t: float) -> dict | None:
    """Position + heading at media time t (seconds)."""
    if not route:
        return None
    if len(route) == 1:
        return {"lat": route[0]["lat"], "lon": route[0]["lon"], "heading": None}
    if t <= route[0]["t"]:
        i = 0
    elif t >= route[-1]["t"]:
        i = len(route) - 2
    else:
        i = max(k for k in range(len(route) - 1) if route[k]["t"] <= t)
    a, b = route[i], route[i + 1]
    span = (b["t"] - a["t"]) or 1e-9
    f = min(1.0, max(0.0, (t - a["t"]) / span))
    lat = a["lat"] + (b["lat"] - a["lat"]) * f
    lon = a["lon"] + (b["lon"] - a["lon"]) * f
    heading = bearing_deg(a["lat"], a["lon"], b["lat"], b["lon"]) if haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) > 0.5 else None
    return {"lat": lat, "lon": lon, "heading": heading}


def route_length_m(route: list[dict]) -> float:
    return sum(haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(route, route[1:]))
