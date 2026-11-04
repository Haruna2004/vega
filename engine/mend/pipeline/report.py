"""Stage 7 — bill of quantities, per-site work orders and the tender (RFQ).

Every number comes from code with the defect id it derives from; Muse Spark only
writes prose sections around the tables. Output: Markdown + HTML (+ PDF when a
Chrome/Chromium binary is available; otherwise the HTML print view is the PDF path).
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import REPO_ROOT, concept as concept_cfg
from ..config import load_unit_rates
from ..prompts import render
from ..store import Run
from . import client

BUCKET_AREA = {"S": 0.25, "M": 0.6, "L": 1.5, "XL": 3.0}
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def effective_rates(run: Run) -> dict:
    base = load_unit_rates()
    override = run.read("unit_rates")
    if override:
        base = {**base, **{k: v for k, v in override.items() if k != "treatments"}}
        for k, v in (override.get("treatments") or {}).items():
            base["treatments"].setdefault(k, {}).update(v)
    return base


def line_for(defect: dict, rates: dict) -> dict:
    c = concept_cfg(defect["concept"])
    tkey = c.get("treatment", "debris_removal")
    t = rates["treatments"].get(tkey, {"label": tkey, "unit": "item", "rate": 0})
    unit = t.get("unit", "item")
    fx = float(rates.get("fx_from_usd", 1.0))
    waste = float(t.get("waste_factor", 1.0))
    min_qty = float(t.get("min_qty", 0))
    basis = ""
    estimated = False
    if unit == "m2":
        area = defect.get("area_m2")
        if area is None:
            area = BUCKET_AREA.get(defect.get("size_bucket") or "M", 0.6)
            estimated = True
            basis = f"{defect['id']}: size bucket {defect.get('size_bucket')} → {area} m² assumed"
        else:
            basis = f"{defect['id']}: {area:.2f} m² measured × {waste} cut/waste"
        qty = max(min_qty, area * waste)
    elif unit == "m":
        length = defect.get("length_m")
        if length is None:
            length = 2.0
            estimated = True
            basis = f"{defect['id']}: length not measurable → 2.0 m assumed"
        else:
            basis = f"{defect['id']}: {length:.1f} m measured × {waste}"
        qty = max(min_qty, length * waste)
    else:
        qty = 1.0
        basis = f"{defect['id']}: 1 item"
    rate = float(t.get("rate", 0)) * fx
    qty = round(qty, 2)
    return {"defect_id": defect["id"], "site_id": defect.get("site_id"), "treatment": tkey, "description": t.get("label", tkey), "unit": unit, "qty": qty, "rate": round(rate, 2), "amount": round(qty * rate, 2), "basis": basis, "estimated": estimated, "severity": defect["severity"]}


def compute_boq(run: Run, rates: dict | None = None) -> dict:
    rates = rates or effective_rates(run)
    defects = [d for d in run.read("defects", []) if not d.get("dismissed") and d.get("site_id")]
    sites = run.read("sites", [])
    fx = float(rates.get("fx_from_usd", 1.0))
    mob = float(rates.get("mobilisation_per_site", 0)) * fx
    lines = [line_for(d, rates) for d in defects]
    per_site = {}
    for s in sites:
        sl = [ln for ln in lines if ln["site_id"] == s["id"]]
        works = round(sum(ln["amount"] for ln in sl), 2)
        per_site[s["id"]] = {"lines": sl, "works": works, "mobilisation": round(mob, 2) if sl else 0.0, "total": round(works + (mob if sl else 0.0), 2)}
    subtotal = round(sum(v["total"] for v in per_site.values()), 2)
    cont = round(subtotal * float(rates.get("contingency_pct", 0)) / 100, 2)
    by_treatment: dict[str, dict] = {}
    for ln in lines:
        b = by_treatment.setdefault(ln["treatment"], {"treatment": ln["treatment"], "description": ln["description"], "unit": ln["unit"], "qty": 0.0, "rate": ln["rate"], "amount": 0.0, "defects": []})
        b["qty"] = round(b["qty"] + ln["qty"], 2)
        b["amount"] = round(b["amount"] + ln["amount"], 2)
        b["defects"].append(ln["defect_id"])
    return {
        "currency": rates.get("currency", "USD"),
        "symbol": rates.get("currency_symbol", "$"),
        "fx_from_usd": fx,
        "contingency_pct": rates.get("contingency_pct", 0),
        "lines": lines,
        "sites": per_site,
        "by_treatment": sorted(by_treatment.values(), key=lambda b: -b["amount"]),
        "subtotal": subtotal,
        "contingency": cont,
        "total": round(subtotal + cont, 2),
        "placeholder_rates": True,
    }


def tender_schema() -> dict:
    keys = ["executive_summary", "scope_of_works", "technical_specifications", "programme", "safety_and_traffic_management", "evidence_note"]
    return {"type": "object", "additionalProperties": False, "properties": {k: {"type": "string"} for k in keys}, "required": keys}


def tender_sections(run: Run, sites: list[dict], defects: dict[str, dict], boq: dict) -> dict:
    meta = run.meta
    authority = (meta.get("settings") or {}).get("authority") or "the Road Authority"
    data = {
        "survey": {"name": meta.get("name"), "country": meta.get("country"), "sites": len(sites), "defects": sum(len(s["defect_ids"]) for s in sites)},
        "treatments": [{k: b[k] for k in ("description", "unit", "qty")} | {"defect_ids": b["defects"]} for b in boq["by_treatment"]],
        "sites": [
            {"id": s["id"], "rank": s.get("rank"), "street": s.get("street"), "road_class": s.get("road_class"), "nearby": [p["name"] + f" ({p['kind']})" for p in s.get("pois", [])[:3]], "defects": [{"id": i, "type": defects[i]["label"], "severity": defects[i]["severity"]} for i in s["defect_ids"] if i in defects]}
            for s in sites[:25]
        ],
    }
    try:
        out = client().spark_json(
            [{"role": "system", "content": render("tender", authority=authority)}, {"role": "user", "content": "Survey data:\n" + json.dumps(data, ensure_ascii=False, indent=1)}],
            tender_schema(),
            name="tender_sections",
            reasoning_effort="medium",
            tag="tender",
        )
        out["_by"] = "muse-spark"
        return out
    except Exception as exc:
        run.log(f"Spark tender prose unavailable: {exc}", level="warn")
        return {
            "executive_summary": f"Survey '{meta.get('name')}' identified {data['survey']['defects']} defects at {len(sites)} sites. Sites are ranked by severity and exposure.",
            "scope_of_works": "Repair the defects listed in the Bill of Quantities, site by site, in rank order.",
            "technical_specifications": "Saw-cut patch edges square; remove loose material; apply tack coat; place and compact asphalt in layers; seal cracks after routing and cleaning.",
            "programme": "Works to start with Rank 1 sites within 14 days of award.",
            "safety_and_traffic_management": "Provide signage, cones and flaggers at every site during works.",
            "evidence_note": "Each defect has a SAM 3.1 segmentation mask, an evidence image and a measurement with its uncertainty range.",
            "_by": "fallback",
        }


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["money"] = lambda v, sym="$": f"{sym}{v:,.2f}"
    env.filters["md"] = lambda text: md.markdown(text or "", extensions=["tables"])
    return env


def find_chrome() -> str | None:
    cands = [os.environ.get("MEND_CHROME")]
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        cands.append(shutil.which(name))
    cands = [cands[0]] + sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/*/chrome-headless-shell"), reverse=True) + cands[1:]
    cands += sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"), reverse=True)
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    for c in cands:
        if c and Path(c).exists():
            return c
    return None


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    chrome = find_chrome()
    if not chrome:
        return False
    # No --user-data-dir: headless Chrome then uses a throwaway profile, and a
    # fresh explicit profile makes full Chrome hang on first-run/sync work.
    headless = "--headless" if "headless-shell" in chrome else "--headless=new"
    cmd = [chrome, headless, "--no-sandbox", "--disable-gpu", "--disable-extensions", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=90)
    except Exception:
        return False
    return pdf_path.exists() and pdf_path.stat().st_size > 1000


def build_documents(run: Run, *, sections: dict | None = None, pdf: bool = True) -> dict:
    rates = effective_rates(run)
    boq = compute_boq(run, rates)
    sites = run.read("sites", [])
    defects = {d["id"]: d for d in run.read("defects", [])}
    meta = run.meta
    sections = sections or run.read("tender_sections") or tender_sections(run, sites, defects, boq)
    run.write("tender_sections", sections)
    env = _env()
    ctx = {
        "run": meta,
        "sites": sites,
        "defects": defects,
        "boq": boq,
        "sections": sections,
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "calibration": run.read("calibration", {}),
        "authority": (meta.get("settings") or {}).get("authority") or "Road Authority",
        "sym": boq["symbol"],
    }
    out_dir = run.dir / "workorders"
    out_dir.mkdir(exist_ok=True)
    docs = []
    for s in sites:
        if not boq["sites"].get(s["id"], {}).get("lines"):
            continue
        sctx = {**ctx, "site": s, "site_boq": boq["sites"][s["id"]]}
        (out_dir / f"{s['id']}.md").write_text(env.get_template("workorder.md.j2").render(**sctx))
        (out_dir / f"{s['id']}.html").write_text(env.get_template("workorder.html.j2").render(**sctx))
        docs.append({"id": s["id"], "kind": "work_order", "site_id": s["id"], "rank": s.get("rank"), "total": boq["sites"][s["id"]]["total"], "md": f"workorders/{s['id']}.md", "html": f"workorders/{s['id']}.html"})
    (out_dir / "tender.md").write_text(env.get_template("tender.md.j2").render(**ctx))
    (out_dir / "tender.html").write_text(env.get_template("tender.html.j2").render(**ctx))
    docs.insert(0, {"id": "tender", "kind": "tender", "total": boq["total"], "md": "workorders/tender.md", "html": "workorders/tender.html"})
    if pdf:
        for d in docs:
            pdf_path = run.dir / d["html"].replace(".html", ".pdf")
            if html_to_pdf(run.dir / d["html"], pdf_path):
                d["pdf"] = run.rel(pdf_path)
    run.write("boq", boq)
    run.write("documents", docs)
    return {"boq": boq, "documents": docs}


def report(run: Run) -> dict:
    run.set_stage("report", "running")
    out = build_documents(run, sections=None, pdf=True)
    boq = out["boq"]
    defects = [d for d in run.read("defects", []) if not d.get("dismissed")]
    summary = {
        "defects": len(defects),
        "sites": len(run.read("sites", [])),
        "area_m2": round(sum(d.get("area_m2") or 0 for d in defects if d.get("quantity_key") != "length_m"), 2),
        "crack_m": round(sum(d.get("length_m") or 0 for d in defects if d.get("quantity_key") == "length_m"), 1),
        "total_cost": boq["total"],
        "currency": boq["currency"],
        "symbol": boq["symbol"],
        "severe": sum(1 for d in defects if d["severity"] >= 4),
        "pdf": any("pdf" in d for d in out["documents"]),
    }
    run.write("summary", summary)
    run.emit("summary", **summary)
    run.set_stage("report", "done", documents=len(out["documents"]), total=boq["total"], pdf=summary["pdf"])
    return out
