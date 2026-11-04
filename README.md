# MEND

Road repair plans from a single drive. Live at **https://mend.harunafaruk.com**

Record a road with a phone or dashcam. MEND outlines and tracks every pothole and crack with **SAM 3.1**, measures each one in square metres, maps it, ranks repairs by risk to people, and writes the work orders and tender. **Muse Spark** plans the scan, reviews every detection, explains the ranking, drafts the tender and answers questions. **Muse Voice Transcribe** turns an inspector's spoken notes into ranking changes.

## How it works

1. **Record**: upload video or photos, or use the Capture page on a phone (logs GPS while filming).
2. **Find and measure**: SAM 3.1 segments and tracks defects across the video; a camera model projects each mask onto the road to get m² with an uncertainty range.
3. **Rank by risk**: severity × exposure (road class, schools, clinics and bus stops from OpenStreetMap, inspector voice notes).
4. **Issue the work**: work orders, bill of quantities and RFQ as PDF, every line tied to a defect image.

## Repo

| Folder | What |
|---|---|
| `frontend/` | Web app (Vite + React + Tailwind + MapLibre): landing page, dashboard, phone capture |
| `engine/` | Python processing pipeline and API (FastAPI, ffmpeg, OpenCV), runs on Google Cloud Run |
| `api/` | Cloudflare Worker: serves the app and results from R2, takes uploads, forwards work to the engine |
| `infra/` | Dockerfile, Cloud Build config, deploy script |
| `config/` | Defect types, unit rates (placeholders), model prompts |
| `docs/` | API shapes, hackathon notes, screenshots |

## Run locally

```bash
uv venv .venv && . .venv/bin/activate && uv pip install -r engine/requirements.txt
cp .env.example .env            # add META_MODEL_API_KEY
(cd frontend && npm install && npm run build)
cd engine && python -m mend serve   # http://localhost:8000
```

Process a video from the command line: `python -m mend run path/to/drive.mp4 --name "My road"`.

## Deploy

`infra/deploy.sh` builds the engine image, deploys it to Cloud Run (scales to zero, max 1 instance), builds the frontend and deploys the Worker.

## Notes

- Unit rates in `config/unit_rates.yaml` are placeholders, not market prices.
- Every Meta API response is cached by content hash, so re-running a survey costs nothing.

## Known limits

- **Sizes are estimates.** Area comes from a single camera and an assumed camera height and field of view, so each defect shows a range, not one exact number. Sizes have not yet been checked against tape measurements on site.
- **Defects cut off by the frame edge are lower bounds.** If a pothole runs out of the picture, MEND can only measure the part it sees.
- **Worn and unpaved roads are harder.** SAM 3.1 text prompts find less on low-contrast gravel than on tarmac.
- **No GPS means a drawn route.** Footage without GPS needs the route drawn on the map, and positions along it assume a steady speed. The demo survey "bolonge" uses a drawn route.
- **Nearby places depend on OpenStreetMap.** When the public Overpass servers are busy, road class and nearby schools, clinics and bus stops show as unknown, and ranking falls back to severity and inspector notes.
- **Unit rates are placeholders.** Costs show the method, not real market prices. Rates can be edited per survey.
- **Speed.** A one-minute clip takes a few minutes to process, and a voice note takes up to about a minute to transcribe and re-rank. The engine scales to zero, so the first request after a quiet period is slower.
