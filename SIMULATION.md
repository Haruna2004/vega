# What is simulated (until a Meta API key is added)

One switch: `MEND_PROVIDER` (`meta` = real models, `simulate` = stand-ins).
Default: `meta` when `META_MODEL_API_KEY` is set, otherwise `simulate`.
All stand-ins live in **one file: `engine/mend/simulate.py`**. The UI shows an
amber **SIMULATED AI** badge on any run made in simulate mode.

| Real model | What runs instead in simulate mode | What stays real |
|---|---|---|
| SAM 3.1 (detect, mask, track) | Classic computer vision on your actual video: dark blobs (pothole-like) and thin dark lines (crack-like) inside the road area, tracked frame to frame by overlap. Output is written in SAM 3.1's exact wire format and parsed by Meta's official parser. | Parsing, track stitching, dedupe, masks, overlays, annotated video, measurement maths, map, ranking, costs, documents |
| Muse Spark (triage) | Every frame marked "road visible, check potholes + cracks" | Chunk planning |
| Muse Spark (camera horizon) | Fixed 0.45 of frame height | Camera model, uncertainty ranges |
| Muse Spark (crop review) | Severity from measured size only; notes say "simulated review" | Rule-based severity factors |
| Muse Spark (ranking rationale, tender text) | Template sentences marked "[simulated]" | All numbers, tables, BoQ |
| Muse Spark (voice-note intent) | Keyword rules (school, kids, hospital, bus, traffic) | Re-ranking, documents |
| Muse Spark (Ask agent) | Keyword router picks a tool; answer is a one-line summary | Tools, tool results, tables, costs |
| Muse Voice Transcribe | Returns a placeholder sentence (you can type the note instead) | Everything after the transcript |

To go real: set `META_MODEL_API_KEY` (Cloud Run env var) and re-run a survey.
Nothing else changes. Every real call is cached in R2, so re-runs cost nothing.

Not simulated anywhere: ffmpeg ingest, GPS/route handling, OpenStreetMap
street names / schools / hospitals, measurement, prioritisation, BoQ, PDF.
