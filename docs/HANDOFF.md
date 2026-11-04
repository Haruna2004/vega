# Handoff: demo video and submission

Read first: `README.md`, `docs/hackathon_page.md` (rules and judging), `DESIGN.md` (UI rules: no em dashes, no unnecessary labels).

## State (Nov 4)
- Live product: https://mend.harunafaruk.com (landing at `/`, platform at `/app`, phone capture at `/capture`).
- Repo: github.com/Haruna2004/vega, `main` = latest. Work happens on branch `mend`, then fast-forward `main`.
- Real Meta models only: Muse Spark 1.3, SAM 3.1 (video + image), Muse Voice Transcribe 1.0. Key lives in `.env` (gitignored) and on Cloud Run. Never commit it.
- Infra: Cloudflare Worker + R2 (free tier) in `api/`; Python engine on Cloud Run project `mend-road-audit-1104`, region europe-west1, scales to zero, max 1 instance, $5 budget alert. Deploy with `infra/deploy.sh`. gcloud needs `env -u CLOUDSDK_AUTH_ACCESS_TOKEN` in this environment.
- Speed: a 1-minute clip processes in about 1.5 to 2 minutes; Ask answers in 3 to 8 s.
- One survey on the live site: "Zaria" (portrait clip found online). SAM 3.1 found no potholes on that worn gravel road; only one "standing water" mask on the verge. Not good demo material, and its licence is unknown.

## What is left
1. **Demo footage**: own recording (or Creative Commons with attribution), landscape, daylight, clear potholes on tarmac, 1 to 2 minutes. Upload via `/app` or record via `/capture`. Rules require footage we own or may use.
2. Optional quality upgrade: Muse Spark marks rough boxes around potholes, SAM 3.1 refines them with box prompts (`meta_sam_parser.build_object_prompt`). Helps on worn roads where text prompts find nothing.
3. Optional: stream Ask answers word by word.
4. Demo video (3 min, show the product working), submission form text, optional X post for Most Viral.
5. Make sure the GitHub repo is public before submitting.

## Demo video outline (3:00, product working, voiceover)
- 0:00 Problem in one line over raw footage of a bad road. (Pitch angle from Haruna: NYC's pothole push under Mayor Mamdani makes this timely. Verify the specifics before saying them on camera.)
- 0:15 Landing page, then `/app`: upload the drive (or show phone capture).
- 0:30 Review: pipeline steps run, SAM 3.1 masks appear on the video, counters climb. Click a defect: size with range, severity reasons, Muse Spark crop review.
- 1:15 Map: road coloured by condition, ranked sites. Open the #1 site.
- 1:35 Voice note on that site ("kids cross here every morning"): transcript appears, rank changes.
- 1:55 Work orders: edit a unit rate, total updates, download the PDF (plain document with signature lines).
- 2:20 Ask: "What would it cost to fix everything near a school?" Answer cites site and defect ids.
- 2:45 Close: what is built on Meta models, live URL.

## Submission form fields to draft
Team name · Track (Indie) · Problem statement (Build for Your World, or Push the Frontier) · Project description · Public GitHub repo · 3-minute video link · Use of Meta products · Why Meta's models are important · optional X post link.
