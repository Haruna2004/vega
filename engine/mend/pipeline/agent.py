"""'Ask the roads': Muse Spark tool-calling over one run.

The model only sees what tools return, and must cite defect/site ids. Every tool
is a pure function over the run's JSON, so answers are reproducible and the
whole exchange (incl. tool results) is returned for the UI to render.
"""

from __future__ import annotations

import json
from typing import Any

from .. import gps
from ..prompts import render
from ..store import Run
from . import client
from .report import compute_boq

MAX_STEPS = 6


def _compact_defect(d: dict) -> dict:
    out = {k: d.get(k) for k in ("id", "site_id", "label", "severity", "position", "method", "dismissed")}
    if d.get("area_m2") is not None and d.get("quantity_key") != "length_m":
        out["area_m2"] = d["area_m2"]
        out["area_range_m2"] = [d.get("conf_low"), d.get("conf_high")]
    elif d.get("length_m") is not None:
        out["length_m"] = d["length_m"]
    else:
        out["size_bucket"] = d.get("size_bucket")
    out["t_s"] = d.get("t")
    return out


class Tools:
    def __init__(self, run: Run):
        self.run = run
        self.defects = {d["id"]: d for d in run.read("defects", [])}
        self.sites = {s["id"]: s for s in run.read("sites", [])}
        self.boq = compute_boq(run)

    # -- tool implementations --------------------------------------------
    def list_sites(self, limit: int = 20) -> list[dict]:
        out = []
        for s in sorted(self.sites.values(), key=lambda s: s.get("rank") or 999)[:limit]:
            ds = [self.defects[i] for i in s["defect_ids"] if i in self.defects]
            out.append({
                "id": s["id"], "rank": s.get("rank"), "priority_score": s.get("priority_score"), "street": s.get("street"),
                "road_class": s.get("road_class"), "defect_ids": s["defect_ids"], "worst_severity": max((d["severity"] for d in ds), default=None),
                "nearby": [{"name": p["name"], "kind": p["kind"], "distance_m": p["distance_m"]} for p in s.get("pois", [])[:4]],
                "site_total_cost": self.boq["sites"].get(s["id"], {}).get("total"), "field_note": (s.get("voice") or {}).get("transcript"),
            })
        return out

    def get_defect(self, defect_id: str) -> dict:
        d = self.defects.get(defect_id)
        if not d:
            return {"error": f"no defect {defect_id}"}
        out = _compact_defect(d)
        out.update({"review": (d.get("review") or {}).get("notes"), "severity_factors": d.get("severity_factors"), "measure_method": d.get("method_detail"), "evidence_image": d.get("evidence"), "lat": d.get("lat"), "lon": d.get("lon")})
        line = next((ln for ln in self.boq["lines"] if ln["defect_id"] == defect_id), None)
        if line:
            out["repair"] = {k: line[k] for k in ("description", "qty", "unit", "rate", "amount")}
        return out

    def get_site(self, site_id: str) -> dict:
        s = self.sites.get(site_id)
        if not s:
            return {"error": f"no site {site_id}"}
        return {k: s.get(k) for k in ("id", "rank", "priority_score", "street", "area", "road_class", "lat", "lon", "factors", "rationale")} | {"pois": s.get("pois", []), "defects": [_compact_defect(self.defects[i]) for i in s["defect_ids"] if i in self.defects], "site_total_cost": self.boq["sites"].get(site_id, {}).get("total")}

    def filter_defects(self, concept: str | None = None, min_severity: int | None = None, position: str | None = None, near_poi: str | None = None, within_m: float | None = None, site_id: str | None = None) -> list[dict]:
        out = []
        for d in self.defects.values():
            if d.get("dismissed"):
                continue
            if concept and concept.lower() not in (d["concept"] + " " + d["label"]).lower():
                continue
            if min_severity and d["severity"] < int(min_severity):
                continue
            if position and d.get("position") != position:
                continue
            if site_id and d.get("site_id") != site_id:
                continue
            if near_poi:
                dist = self._poi_distance(d, near_poi)
                if dist is None or dist > float(within_m or 150):
                    continue
                c = _compact_defect(d)
                c["poi_distance_m"] = round(dist)
                out.append(c)
                continue
            out.append(_compact_defect(d))
        return out

    def _poi_distance(self, d: dict, kind: str) -> float | None:
        s = self.sites.get(d.get("site_id") or "")
        if not s:
            return None
        kind = kind.lower().replace(" ", "_").rstrip("s") if kind.lower() not in ("bus_stop", "bus stop") else "bus_stop"
        best = None
        for p in s.get("pois", []):
            if p["kind"] == kind or (kind == "school" and p["kind"] == "school"):
                dist = gps.haversine_m(d.get("lat") or s["lat"], d.get("lon") or s["lon"], p["lat"], p["lon"])
                best = dist if best is None else min(best, dist)
        intent = (s.get("voice") or {}).get("intent") or {}
        if best is None and intent.get(f"near_{kind}"):
            best = 0.0  # reported by the inspector's voice note
        return best

    def sum_cost(self, defect_ids: list[str] | None = None, site_ids: list[str] | None = None) -> dict:
        ids = set(defect_ids or [])
        if site_ids:
            for sid in site_ids:
                ids.update((self.sites.get(sid) or {}).get("defect_ids", []))
        lines = [ln for ln in self.boq["lines"] if ln["defect_id"] in ids]
        works = round(sum(ln["amount"] for ln in lines), 2)
        site_set = sorted({ln["site_id"] for ln in lines if ln["site_id"]})
        mob = round(sum(self.boq["sites"][s]["mobilisation"] for s in site_set if s in self.boq["sites"]), 2)
        cont = round((works + mob) * float(self.boq["contingency_pct"]) / 100, 2)
        return {"currency": self.boq["currency"], "defects": sorted(ids), "sites": site_set, "works": works, "mobilisation": mob, "contingency": cont, "total": round(works + mob + cont, 2), "lines": [{k: ln[k] for k in ("defect_id", "description", "qty", "unit", "amount")} for ln in lines], "note": "unit rates are placeholders"}

    def top_n(self, n: int = 5, by: str = "priority") -> list[dict]:
        if by == "priority":
            return self.list_sites(limit=int(n))
        ds = [d for d in self.defects.values() if not d.get("dismissed")]
        key = {"severity": lambda d: (d["severity"], d.get("area_m2") or 0), "area": lambda d: d.get("area_m2") or 0, "cost": lambda d: next((ln["amount"] for ln in self.boq["lines"] if ln["defect_id"] == d["id"]), 0)}.get(by, lambda d: d["severity"])
        return [_compact_defect(d) for d in sorted(ds, key=key, reverse=True)[: int(n)]]

    def show_frame(self, defect_id: str) -> dict:
        d = self.defects.get(defect_id)
        if not d:
            return {"error": f"no defect {defect_id}"}
        return {"defect_id": defect_id, "image": d.get("evidence_frame"), "crop": d.get("evidence"), "t_s": d.get("t"), "frame": d.get("best_frame")}

    # -- schema -----------------------------------------------------------
    @staticmethod
    def schemas() -> list[dict]:
        def fn(name, desc, props, required=()):
            return {"type": "function", "function": {"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": list(required)}}}

        return [
            fn("list_sites", "Sites ranked by repair priority, with street, defects, nearby schools/hospitals/bus stops and site cost.", {"limit": {"type": "integer"}}),
            fn("get_site", "Full detail for one site (S01...).", {"site_id": {"type": "string"}}, ["site_id"]),
            fn("get_defect", "Full detail for one defect (D001...): size with range, severity factors, review notes, repair line.", {"defect_id": {"type": "string"}}, ["defect_id"]),
            fn("filter_defects", "Defects matching filters. near_poi: school | hospital | bus_stop | market, with within_m metres.", {"concept": {"type": "string"}, "min_severity": {"type": "integer"}, "position": {"type": "string", "enum": ["wheel_path", "centre", "edge"]}, "near_poi": {"type": "string"}, "within_m": {"type": "number"}, "site_id": {"type": "string"}}),
            fn("sum_cost", "Cost to repair the given defects and/or all defects at the given sites (works + mobilisation + contingency).", {"defect_ids": {"type": "array", "items": {"type": "string"}}, "site_ids": {"type": "array", "items": {"type": "string"}}}),
            fn("top_n", "Top n sites by priority, or top n defects by severity / area / cost.", {"n": {"type": "integer"}, "by": {"type": "string", "enum": ["priority", "severity", "area", "cost"]}}),
            fn("show_frame", "Evidence image (video frame with SAM mask) for a defect, shown to the user.", {"defect_id": {"type": "string"}}, ["defect_id"]),
        ]

    def call(self, name: str, args: dict) -> Any:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name in ("call", "schemas"):
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except TypeError as exc:
            return {"error": f"bad arguments: {exc}"}


def ask(run: Run, question: str, history: list[dict] | None = None) -> dict:
    tools = Tools(run)
    summary = run.read("summary", {})
    # Compact survey table in the prompt: most questions are answered in one call, no tool round-trip.
    digest = {"summary": summary, "sites": tools.list_sites(limit=30), "defects": [_compact_defect(d) for d in tools.defects.values() if not d.get("dismissed")][:80]}
    system = render("agent_system", currency=summary.get("currency", "USD"), summary=json.dumps(digest, ensure_ascii=False))
    messages: list[dict] = [{"role": "system", "content": system}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})
    steps: list[dict] = []
    answer = ""
    for _ in range(MAX_STEPS):
        resp = client().spark_chat(messages, tools=Tools.schemas(), reasoning_effort="minimal", tag="agent")
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            answer = msg.get("content") or ""
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["function"]["name"], "arguments": c["function"].get("arguments") or "{}"}} for c in calls]})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = tools.call(name, args)
            steps.append({"tool": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, ensure_ascii=False)})
    else:
        answer = answer or "I could not finish within the tool-call budget."
    import re

    answer = answer.replace("\u2014", ", ").replace("\u2013", "-")
    cited = sorted(set(re.findall(r"\b[DS]\d{2,3}\b", answer)))
    return {"question": question, "answer": answer, "steps": steps, "cited": cited}
