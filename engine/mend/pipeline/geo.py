"""Stage 5, geolocate defects, cluster them into sites, enrich from OpenStreetMap.

Each defect gets the camera position at its best frame, pushed forward by the
measured ground distance and sideways by the lateral offset (when the route
gives a heading). Defects within 8 m form one site. Street names come from
Nominatim, road class + nearby schools / hospitals / bus stops from one Overpass
query over the whole route. All lookups are cached; offline = cache only.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict

import httpx

from .. import gps
from ..config import get_settings
from ..meta_client import DiskCache, request_key
from ..store import Run

CLUSTER_M = 8.0
POI_RADIUS_M = 150.0  # counts towards exposure
POI_STORE_RADIUS_M = 300.0  # kept for questions like "within 200 m of a school"
ROAD_CLASS_WEIGHT = {
    "motorway": 1.0, "trunk": 1.0, "primary": 1.0, "secondary": 0.85, "tertiary": 0.7,
    "unclassified": 0.55, "residential": 0.5, "living_street": 0.45, "service": 0.35, "track": 0.3, "unknown": 0.6,
}
POI_KINDS = {
    "school": ["school", "kindergarten", "college", "university"],
    "hospital": ["hospital", "clinic", "doctors"],
    "bus_stop": [],
    "market": ["marketplace"],
    "place_of_worship": ["place_of_worship"],
}


def _cache() -> DiskCache:
    return DiskCache(get_settings().cache_dir)


def _http_get_json(kind: str, url: str, params: dict, *, offline: bool) -> dict | list | None:
    key = request_key(kind, {"url": url, "params": params})
    cache = _cache()
    hit = cache.get(kind, key)
    if hit is not None:
        return hit["response"]
    if offline or get_settings().geocoder == "off":
        return None
    s = get_settings()
    try:
        r = httpx.get(url, params=params, headers={"User-Agent": s.user_agent}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    cache.put(kind, key, {"url": url, "params": params, "response": data, "created_at": time.time()})
    return data


def reverse_geocode(lat: float, lon: float, offline: bool) -> dict | None:
    s = get_settings()
    data = _http_get_json("nominatim", f"{s.nominatim_url}/reverse", {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "format": "jsonv2", "zoom": 17, "addressdetails": 1}, offline=offline)
    if not isinstance(data, dict) or "error" in data:
        return None
    addr = data.get("address", {})
    street = addr.get("road") or addr.get("pedestrian") or addr.get("street") or data.get("name")
    area = addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district") or addr.get("town") or addr.get("city") or addr.get("village")
    return {"street": street, "area": area, "city": addr.get("city") or addr.get("town") or addr.get("state"), "display_name": data.get("display_name")}


def overpass(bbox: tuple[float, float, float, float], offline: bool) -> dict | None:
    s = get_settings()
    south, west, north, east = bbox
    b = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    q = f"""[out:json][timeout:60];
(
  way["highway"]({b});
  nwr["amenity"~"^(school|kindergarten|college|university|hospital|clinic|doctors|marketplace|place_of_worship)$"]({b});
  node["highway"="bus_stop"]({b});
  node["public_transport"="platform"]({b});
);
out tags center geom;"""
    data = _http_get_json("overpass", s.overpass_url, {"data": q}, offline=offline)
    return data if isinstance(data, dict) else None


def _point_seg_dist_m(lat, lon, a, b) -> float:
    # local equirectangular projection (fine at <1 km scale)
    kx = 111320 * math.cos(math.radians(lat))
    ky = 110540
    px, py = 0.0, 0.0
    ax, ay = (a[1] - lon) * kx, (a[0] - lat) * ky
    bx, by = (b[1] - lon) * kx, (b[0] - lat) * ky
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(cx - px, cy - py)


def osm_context(lat: float, lon: float, osm: dict | None) -> dict:
    if not osm:
        return {"road_class": "unknown", "road_name": None, "pois": []}
    best = (1e9, None)
    pois = []
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        if el.get("type") == "way" and "highway" in tags and el.get("geometry"):
            geom = [(p["lat"], p["lon"]) for p in el["geometry"]]
            for a, b in zip(geom, geom[1:]):
                d = _point_seg_dist_m(lat, lon, a, b)
                if d < best[0]:
                    best = (d, tags)
        kind = None
        amenity = tags.get("amenity")
        for k, vals in POI_KINDS.items():
            if amenity in vals:
                kind = k
        if tags.get("highway") == "bus_stop" or tags.get("public_transport") == "platform":
            kind = "bus_stop"
        if kind:
            plat = el.get("lat") or (el.get("center") or {}).get("lat")
            plon = el.get("lon") or (el.get("center") or {}).get("lon")
            if plat is None:
                continue
            d = gps.haversine_m(lat, lon, plat, plon)
            if d <= POI_STORE_RADIUS_M:
                pois.append({"kind": kind, "name": tags.get("name") or kind.replace("_", " ").title(), "distance_m": round(d), "lat": plat, "lon": plon, "osm_id": f"{el['type']}/{el['id']}"})
    road_tags = best[1] or {}
    hw = road_tags.get("highway", "unknown")
    hw = hw.replace("_link", "")
    pois.sort(key=lambda p: p["distance_m"])
    dedup, seen = [], set()
    for p in pois:
        k = (p["kind"], p["name"])
        if k not in seen:
            seen.add(k)
            dedup.append(p)
    return {"road_class": hw if hw in ROAD_CLASS_WEIGHT else "unknown", "road_name": road_tags.get("name"), "road_distance_m": round(best[0], 1) if best[1] else None, "pois": dedup[:10]}


def locate_defects(run: Run, defects: list[dict], media: list[dict], routes: dict) -> int:
    located = 0
    by_media = {m["media_id"]: m for m in media}
    for d in defects:
        r = routes.get(d["media_id"]) or {}
        pts = r.get("points") or []
        d.pop("lat", None)
        d.pop("lon", None)
        if not pts:
            continue
        m = by_media[d["media_id"]]
        t = d["best_frame"] / m["fps"] if m.get("fps") else 0.0
        pos = gps.interpolate(pts, t)
        if not pos:
            continue
        lat, lon = pos["lat"], pos["lon"]
        if pos.get("heading") is not None and d.get("distance_m"):
            lat, lon = gps.offset_point(lat, lon, pos["heading"], d["distance_m"])
            if d.get("lateral_m"):
                lat, lon = gps.offset_point(lat, lon, (pos["heading"] + 90) % 360, d["lateral_m"])
        d["lat"], d["lon"] = round(lat, 7), round(lon, 7)
        d["gps_source"] = r.get("source")
        located += 1
    return located


def cluster(defects: list[dict], radius_m: float = CLUSTER_M) -> list[list[dict]]:
    pts = [d for d in defects if d.get("lat") is not None and not d.get("dismissed")]
    parent = list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if gps.haversine_m(pts[i]["lat"], pts[i]["lon"], pts[j]["lat"], pts[j]["lon"]) <= radius_m:
                parent[find(j)] = find(i)
    groups: dict[int, list[dict]] = defaultdict(list)
    for i, d in enumerate(pts):
        groups[find(i)].append(d)
    return sorted(groups.values(), key=lambda g: (g[0]["media_id"], min(d["t"] for d in g)))


def geo(run: Run) -> dict:
    run.set_stage("geo", "running")
    s = get_settings()
    offline = s.offline
    media = run.read("media")
    routes = run.read("route", {})
    defects = run.read("defects", [])
    located = locate_defects(run, defects, media, routes)
    groups = cluster(defects)
    sites = []
    osm = None
    if groups:
        lats = [d["lat"] for g in groups for d in g]
        lons = [d["lon"] for g in groups for d in g]
        pad_lat = POI_STORE_RADIUS_M / 110540 + 0.0005
        pad_lon = POI_STORE_RADIUS_M / (111320 * math.cos(math.radians(sum(lats) / len(lats)))) + 0.0005
        osm = overpass((min(lats) - pad_lat, min(lons) - pad_lon, max(lats) + pad_lat, max(lons) + pad_lon), offline)
        if osm is None:
            run.log("OpenStreetMap context unavailable (offline or blocked); road class and POIs unknown", level="warn")
    for i, g in enumerate(groups, 1):
        lat = sum(d["lat"] for d in g) / len(g)
        lon = sum(d["lon"] for d in g) / len(g)
        site_id = f"S{i:02d}"
        for d in g:
            d["site_id"] = site_id
        ctx = osm_context(lat, lon, osm)
        addr = reverse_geocode(lat, lon, offline) if i <= 60 else None
        if addr is None and not offline:
            time.sleep(0)  # no-op; Nominatim pacing handled below
        site = {
            "id": site_id,
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "media_id": g[0]["media_id"],
            "t": min(d["t"] for d in g),
            "defect_ids": [d["id"] for d in sorted(g, key=lambda d: -d["severity"])],
            "street": (addr or {}).get("street") or ctx.get("road_name"),
            "area": (addr or {}).get("area"),
            "city": (addr or {}).get("city"),
            "address": (addr or {}).get("display_name"),
            **ctx,
        }
        sites.append(site)
        run.emit("site", site={k: site[k] for k in ("id", "lat", "lon", "street", "road_class", "defect_ids")})
        if not offline and addr is not None:
            time.sleep(1.05)  # Nominatim usage policy: max 1 request/second
    run.write("defects", defects)
    run.write("sites", sites)
    needs_route = [mid for mid, r in routes.items() if not r.get("points") or r.get("needs_route")]
    run.set_stage("geo", "done", located=located, sites=len(sites), needs_route=needs_route, osm=bool(osm))
    return {"sites": sites}


def set_drawn_route(run: Run, media_id: str, points: list[dict]) -> None:
    """Route drawn on the map (start->end waypoints): constant-speed interpolation."""
    media = {m["media_id"]: m for m in run.read("media")}
    routes = run.read("route", {})
    m = media[media_id]
    routes[media_id] = {"source": "drawn_route", "points": gps.polyline_over_time(points, m.get("duration_s") or 0.0), "waypoints": points}
    run.write("route", routes)
    sources = sorted({r.get("source", "none") for r in routes.values()})
    run.update_meta(gps_source="+".join(sources))
