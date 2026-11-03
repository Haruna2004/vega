# SPEC.md — MEND: AI Road Defect Auditor (Meta Global AI Developer Hackathon 2026)

> Original spec from the brainstorming session, kept verbatim. Where reality differed
> (API shapes, network, credits), the build follows DECISIONS.md.

## 0. Read this first (for Claude Code)
You are building a complete, demo-ready product. No human will clarify mid-build. Make sensible decisions, write them in DECISIONS.md, keep going.
Priorities, in order: (1) a working end-to-end pipeline on real footage, (2) a stunning demo video, (3) visible, creative use of Meta's models, (4) code quality.
Before writing app code: read these docs and confirm exact request/response shapes with a smoke test script (`scripts/smoke_meta_api.py`):
- https://dev.meta.ai/docs  (Meta Model API home)
- https://dev.meta.ai/docs/media-segmentation  (SAM 3.1 overview)
- https://dev.meta.ai/docs/sam/segmenting  (SAM 3.1 prompts, video, tracking)
- Also read the SAM docs pages linked from there: "Reading segmentation output" and "Use the client libraries".
- Muse Spark image/video understanding and Muse Voice Transcribe pages (find via docs nav).
If a doc contradicts this spec, the doc wins. Note it in DECISIONS.md.

## 1. One-liner
Upload phone or dashcam footage of roads. MEND finds every pothole, crack and hazard with SAM 3.1, measures it, pins it on a map, ranks repairs by risk, and writes the repair work order and tender. Minutes instead of weeks. Every defect has pixel-level evidence.

## 2. Hackathon context (this decides what to build)
- Event: Meta Global AI Developer Hackathon, run by Meta Superintelligence Labs + Cerebral Valley. Virtual.
- Submission deadline: Nov 4, 2026, 9:00 PM ET. Judging Nov 4–8. Finals Nov 9.
- Final judging weights: Impact 30%, creative use of Meta AI tooling 25%, Demo incl. video 25%, Technical depth & execution 20%.
- Tracks: Indie (creativity, ambition, does it work) or Startup (execution, production-ready). Theme: "Push the Frontier" (physical systems, manufacturing, energy, materials) or "Build for Your World" (a domain you know). Default to Push the Frontier; the write-up template below has both.
- Precedent: a similar project (TARA, road appraisal from Uganda dashcam footage, text-model only) won a prize at the same organizer's Opus 4.6 hackathon. We beat it with pixel-level segmentation, measurement, mapping, prioritization and generated tenders.
- Judges watch a video. The live-processing view and the map are the money shots.

## 3. Meta stack (all through Meta Model API)
- Base URL: `https://api.meta.ai/v1`. OpenAI-compatible. Use the official `openai` SDK with `base_url` set. Also supports Responses API (`/v1/responses`) and Anthropic-style `/v1/messages`.
- Env var: `META_MODEL_API_KEY`. Never hardcode. `.env.example` must list every var.
- Models:
  - `muse-spark-1.3` — multimodal reasoning (text, image, video, audio, PDF in; text out; 1M context; tool calling; structured output / JSON). Use for triage, measurement reasoning, prioritization explanations, tender writing, chat agent. `muse-spark-1.3-contributor` is cheaper but Meta may train on it — use only for non-sensitive test runs if credits run low.
  - `sam-3.1` — text-prompted detection + pixel masks + video tracking. Called via Responses API (`POST /v1/responses`, streams SSE). Input: image (`input_image`) or video (`input_video` as `video_url` or `file_id` via Files API). Prompt: short noun phrase, e.g. "pothole". Returns per match: bounding box, mask, confidence; in video, a persistent track id across frames. This is the star of the demo.
  - `muse-voice-transcribe-1.0` — speech to text. Use for field voice notes.
  - Muse Image — image generation/edit. Stretch: render "after repair" preview of a defect.
  - Muse Glimmer — check docs; if it is a small/fast model, use it for cheap per-frame triage.
- Credits: team has $150 API credits. Cache EVERY API response to disk keyed by content hash + prompt. Demo must run fully from cache with `MEND_OFFLINE=1`. Never re-call the API for the same frame+prompt.
- Open-weights fallback: Muse Spark Open (816B MoE, 1M ctx) exists for on-prem; mention in write-up as the "runs inside a ministry, data never leaves" story. Do not build it.

## 4. Users and impact story
Primary user: a road maintenance engineer at a city or ministry. Today: drive, look, write notes, estimate by eye, build a tender over weeks. With MEND: upload a drive, get a prioritized, costed, evidence-backed work order in minutes. Secondary: insurers, cycling/walking safety groups, utilities (same pipeline, different prompts).

## 5. Demo footage
- User will put footage in a Google Drive folder. Two access paths; support both:
  1. If a Google Drive MCP/connector is available in Claude Code, list the folder and download to `data/raw/`.
  2. Otherwise the user downloads files manually into `data/raw/`. Document this in README.
- Expected: phone or dashcam `.mp4/.mov`, maybe photos `.jpg/.heic`. Some may have GPS (EXIF on photos, GPMF/QuickTime metadata on video, or a separate `.gpx`). Many will have none.
- Also include 2–3 public-domain road images in `data/samples/` so tests run without the user's footage.

## 6. Pipeline (the core)
Stages are independent CLI steps AND run as one background job from the UI. Each stage writes JSON to `data/runs/<run_id>/`.

### 6.1 Ingest
- Input: video/photos + optional GPX/CSV route.
- Extract frames with ffmpeg at 2 fps (configurable). Store frame index, timestamp, path.
- GPS: try EXIF (photos), video metadata (exiftool / ffprobe), GPX file. If none: UI lets the user draw the route on the map (start→end polyline, or a few waypoints) and we interpolate by time. Store `gps_source`.
- Compute a stable `media_id` (sha256).

### 6.2 Triage (Muse Spark 1.3)
- For every Nth frame (default every 2s), send the frame to Muse Spark with a strict JSON schema: `{road_visible: bool, surface_type, weather, lighting, defect_concepts: [string], notes}`. Concept vocabulary (closed list, extendable): pothole, alligator crack, longitudinal crack, transverse crack, rutting, edge break, missing manhole cover, open drain, debris, standing water, faded lane marking, damaged sign, broken speed bump, construction hazard.
- Purpose: decide WHICH SAM prompts to run on which segments of video. Saves credits and improves precision.
- Batch frames where the API allows multiple images per request.

### 6.3 Segment (SAM 3.1) — the star
- For each video segment and each concept flagged by triage, call `sam-3.1` with the concept as the text prompt. Prefer video input so we get track ids (one pothole seen across 40 frames = one defect, not 40).
- Also run a baseline pass with the 3 most common prompts ("pothole", "crack", "standing water") on all segments so nothing is missed.
- Store per detection: track_id, frame_ids, boxes, mask (RLE or PNG), confidence.
- Render overlays: colored mask + outline + label on each frame. Produce an annotated MP4 (`annotated.mp4`) using ffmpeg. This video is the hero of the demo.
- Dedupe tracks across prompts (IoU > 0.6 same frames → merge, keep the more specific label).

### 6.4 Measure
- Estimate real-world size per defect. Methods, best available first:
  1. Calibrated: user supplies camera height + focal/FOV (from phone model EXIF) → ground-plane homography → mask area in m².
  2. Reference-object: SAM also segments "lane marking" / "road lane"; assume lane width 3.5 m (configurable per country) to derive pixels-per-meter at that depth.
  3. Fallback: relative size bucket (S/M/L/XL) from mask area ÷ road-mask area at that frame.
- Output: `area_m2`, `width_m`, `length_m`, `method`, `confidence_low/high`.
- Severity 1–5: rules from area, depth proxy (shadow/edge contrast via Muse Spark judgment on the crop), location (in wheel path vs edge), concept.

### 6.5 Geolocate & cluster
- Assign each track its GPS at first-seen frame. Cluster within 8 m into one "site". A site can hold many defects.
- Reverse-geocode street names with OpenStreetMap Nominatim (free, rate-limit, cache). Offline fallback: coordinates only.

### 6.6 Prioritize
- Priority score = severity × exposure. Exposure proxies: road class from OSM tags (primary/secondary/residential), near school/hospital/bus stop (OSM POIs within 150 m), defect density of the site.
- Muse Spark writes a one-paragraph "why this is #1" for the top 10, citing the numbers.

### 6.7 Work order & tender (Muse Spark 1.3)
- Generate per site and per run:
  - Work Order: site, map link, defects table (type, size, severity, evidence image), recommended treatment (pothole patch, crack seal, overlay, drain clear), quantities.
  - Bill of Quantities + cost estimate from an editable `config/unit_rates.yaml` (default rates in USD/m² with a note they are placeholders; allow currency setting).
  - Tender/RFQ document: scope, specs, timeline, evidence appendix.
- Output Markdown + PDF (render via a headless browser or weasyprint). Every number traceable to a defect id.

### 6.8 Voice field notes (Muse Voice Transcribe)
- UI: hold-to-record on any defect or site. Transcribe. Muse Spark extracts structured intent (e.g. "near a school, kids cross here" → raises exposure, adds tag). Shows in the work order. This is the "creative tooling" bonus; keep it simple and reliable.

### 6.9 "Ask the roads" agent
- Chat over the run with Muse Spark tool-calling: tools `list_sites`, `get_defect`, `filter`, `sum_cost`, `top_n`, `show_frame`. Answers must cite defect ids. Example demo question: "What would it cost to fix everything within 200 m of a school?"

### 6.10 Stretch (only after everything above is solid)
- Muse Image: "after repair" preview of a frame (inpaint defect area). Label clearly as AI render.
- Before/after comparison of two drives of the same road (track deterioration).
- Export GeoJSON / CSV for GIS teams.

## 7. Web app
- Stack: Next.js (App Router) + Tailwind + a Python FastAPI backend for the pipeline (OpenCV, ffmpeg, numpy, shapely). SQLite via SQLModel. Single `docker compose up` and also `make dev`.
- Theme: dark, high-contrast, "mission control". Mask colors by concept; severity on a cold→hot scale. Smooth animations. Must look great in a screen recording at 1080p. Mobile not required.
- Screens:
  1. **New Run**: drag-drop footage, optional GPX, calibration fields, country/currency, "Start".
  2. **Live Processing** (hero): the video plays while masks and labels appear frame by frame as SAM results stream in; side panel counters tick up (defects found, m² of damage, estimated cost). Progress for each stage. Make this cinematic.
  3. **Map**: route polyline, site markers sized by priority, glow on top-10, click → site card. Map library: MapLibre with OSM tiles (no key needed).
  4. **Defects**: table + gallery; each defect shows annotated crop, mask toggle, measurements with confidence, severity, notes, voice-note player.
  5. **Work Orders**: ranked list; open → document view; download PDF/MD; edit unit rates live and watch totals update.
  6. **Ask**: chat with tool results rendered as tables/images.
- Reproducibility: every screen works from a saved run in `data/runs/demo/` with `MEND_OFFLINE=1`.

## 8. Data model (SQLite)
run(id, created_at, name, source_files, gps_source, calibration, currency, status)
frame(id, run_id, idx, t_ms, path, lat, lon)
detection(id, run_id, track_id, concept, frame_ids[], boxes[], mask_path, confidence, merged_from[])
defect(id, run_id, site_id, concept, area_m2, width_m, length_m, measure_method, conf_low, conf_high, severity, evidence_frame_id, evidence_image_path, notes, voice_note_path, transcript)
site(id, run_id, lat, lon, street, road_class, pois[], priority_score, rationale)
work_order(id, run_id, site_id, markdown_path, pdf_path, cost_total, line_items[])
api_cache(hash, model, request_json_path, response_json_path, created_at)

## 9. Repo layout
```
mend/
  SPEC.md  DECISIONS.md  README.md  .env.example  Makefile  docker-compose.yml
  backend/   (FastAPI; pipeline/ ingest.py triage.py segment.py measure.py geo.py prioritize.py report.py voice.py agent.py; meta_client.py with caching; models.py; api.py)
  frontend/  (Next.js app)
  config/    unit_rates.yaml  concepts.yaml  prompts/*.md
  scripts/   smoke_meta_api.py  make_demo_run.py  render_annotated_video.py
  data/      raw/ samples/ runs/ cache/   (gitignored except samples/)
  tests/     unit + an e2e test on data/samples
  docs/      demo_script.md  submission.md  architecture.png
```

## 10. Build order (do not skip ahead)
1. `scripts/smoke_meta_api.py`: one Muse Spark call, one SAM 3.1 image call, one SAM 3.1 video call, one transcribe call. Print raw responses. Save to `docs/api_shapes.md`. Fix `meta_client.py` to match reality.
2. Ingest + frame extraction + GPS parsing. Tests.
3. SAM segment on samples → overlays → annotated video. Get this visually perfect before anything else.
4. Triage (Spark) to choose prompts. Measure. Severity.
5. Geo + clustering + map UI.
6. Prioritize + work order + tender + PDF.
7. Live Processing screen with streaming updates (SSE/WebSocket from backend).
8. Voice notes. Ask agent.
9. Run the full pipeline on the user's real footage in `data/raw/`. Save as `data/runs/demo/`. Offline mode verified.
10. Polish UI. Record demo. Write submission.
11. Stretch items.
Commit after each step. Keep `make demo` working at all times.

## 11. Demo video (2 minutes, 1080p, screen recording + voiceover script in docs/demo_script.md)
0:00 Hook: raw phone footage of a bad road. "A city engineer sees this. The tender takes 6 weeks."
0:10 Drop footage into MEND. Click Start.
0:15 Live Processing: masks light up potholes and cracks in real time, counters climb. (20 seconds, no talking over the visuals except one line: "SAM 3.1 finds every defect, pixel by pixel.")
0:40 Map: markers, top-10 glow. Click the #1 site. "Severity 5, 2.3 m², in the wheel path, 90 m from a primary school."
1:00 Voice note: "kids cross here every morning." Transcript appears, priority bumps.
1:15 Work Orders: open the tender, scroll BoQ, change a unit rate, total updates. Download PDF.
1:35 Ask: "cost to fix everything near schools?" → answer with cited defect ids.
1:50 Close: "Weeks to minutes. Every repair backed by evidence. Built on Muse Spark, SAM 3.1 and Muse Voice Transcribe." Logo.

## 12. Submission write-up (docs/submission.md)
- Title, one-liner, track, theme.
- Problem (2–3 sentences, with a real number about road maintenance backlog if easily sourced; otherwise none).
- What it does (bullets mapping to screens).
- How it uses Meta tools (explicit: Spark for triage/measurement reasoning/tender/agent; SAM 3.1 for detection+masks+tracking; Voice Transcribe for field notes; Muse Image if built; note Muse Spark Open for on-prem deployment).
- Technical depth (homography measurement, track dedupe, clustering, caching, offline reproducibility).
- Impact and what's next (fleet dashcams, before/after drives, other defect domains: pavements, bridges, power lines).
- Links: repo, video, live demo if deployed.
- Team.

## 13. Quality bar
- `make test` green. `make demo` boots the app with the saved run in under 30 s with no network.
- No API call without cache check. Log cost per run.
- Every number shown has a tooltip with method + confidence. Never present a guess as a measurement.
- README covers setup in 5 commands.
- Keep DECISIONS.md honest: what works, what is estimated, what is mocked (nothing in the demo should be mocked except unit rates, which are labelled placeholders).

## 14. Risks and fallbacks
- SAM video API limits (size/length): split videos into ≤30 s chunks; if video endpoint fails, fall back to per-frame image calls and do our own tracking by IoU between consecutive frames.
- No GPS in footage: route-draw tool (already specified). Demo must still look great with it.
- Low SAM recall on faint cracks: run Spark triage with crops at 2× zoom and re-prompt SAM with more specific phrases ("thin crack in asphalt").
- Credits exhausted: offline mode + cache. Keep a `data/runs/demo/` snapshot committed via git-lfs or a release zip.
- PDF rendering issues: Markdown download is the fallback; HTML print view always works.

## 15. Nice touches that win demos
- Counter animation on m² and $ while processing.
- Mask outline "draw-on" animation when a defect is first found.
- Severity heat glow on map markers.
- A "share" button that exports a one-page site card PNG.
- Keyboard shortcut to jump to next defect in the annotated video.
