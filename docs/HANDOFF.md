# Handoff: demo video and submission

Read first: `README.md`, `docs/hackathon_page.md` (rules and judging), `DESIGN.md` (UI rules: no em dashes, no unnecessary labels).

## State (Nov 4)
- Live product: https://mend.harunafaruk.com (landing at `/`, platform at `/app`, phone capture at `/capture`).
- Repo: github.com/Haruna2004/vega, `main` = latest. Work happens on branch `mend`, then fast-forward `main`.
- Real Meta models only: Muse Spark 1.3, SAM 3.1 (video + image), Muse Voice Transcribe 1.0. Key lives in `.env` (gitignored) and on Cloud Run. Never commit it.
- Infra: Cloudflare Worker + R2 (free tier) in `api/`; Python engine on Cloud Run project `mend-road-audit-1104`, region europe-west1, scales to zero, max 1 instance, $5 budget alert. Deploy with `infra/deploy.sh`. gcloud needs `env -u CLOUDSDK_AUTH_ACCESS_TOKEN` in this environment.
- Speed: a 1-minute clip processes in about 1.5 to 2 minutes; Ask answers in 3 to 8 s.
- One survey on the live site: "Zaria" (portrait clip found online). SAM 3.1 found no potholes on that worn gravel road; only one "standing water" mask on the verge. Not good demo material, and its licence is unknown.

## Update (Nov 4, evening)
- Demo survey: "bolonge" (`20261104-160433-bolonge`), drawn route in Samaru, 37 defects, 5 sites.
- Demo video rendered with Remotion (`video/`) and live at https://mend.harunafaruk.com/download/mend-demo.mp4. Rebuild: `cd video && node rec/scenes.js s2 ... s8`, `python3 scripts/build_scenes.py`, `npx remotion render src/index.ts Mend out/mend-demo.mp4 --browser-executable=<chrome-headless-shell>`.
- Fixes today: horizon estimates above 0.15 of the frame were rejected (sizes were 10 to 100 times too big); drawn routes were overwritten on reprocessing; Overpass now POST with mirrors (public servers were timing out, so road class and POIs are unknown on bolonge); voice notes return after re-ranking and rebuild PDFs in the background; Ask renders bold and bullets.
- Unit rate for pothole patching on bolonge was set to 95 during recording (Work orders, "Reset to defaults" to undo).

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
- 2:20 Ask: "Which site should we fix first, and what will it cost?" Answer cites site and defect ids.
- 2:45 Close: what is built on Meta models, live URL.

## Submission form fields to draft
Team name · Track (Indie) · Problem statement (Build for Your World, or Push the Frontier) · Project description · Public GitHub repo · 3-minute video link · Use of Meta products · Why Meta's models are important · optional X post link.

## Making the demo video (agent instructions)

Goal: a finished 1080p MP4 under 3:00 that shows the real product working, with voiceover, captions and light motion design in the MEND style (`DESIGN.md`: mist #f6f8f7, ink, carbon #0f0e12, hairlines, amber #f0a800 accent, 0px radius, Inter, no em dashes).

Secrets (set by Haruna as environment variables, never committed):
- `META_MODEL_API_KEY` (Meta models), `GEMINI_API_KEY` (voiceover), `MEND_ENGINE_KEY` (lets this session read and write R2 through the Worker).
- `MEND_ENGINE_KEY` is a value Haruna chooses. Make the deployment use it: in `api/` run `wrangler secret put ENGINE_KEY` with that value, and update the Cloud Run env var `MEND_ENGINE_KEY` to the same value (`gcloud run services update mend-engine --region europe-west1 --update-env-vars MEND_ENGINE_KEY=...`, project `mend-road-audit-1104`; gcloud needs `env -u CLOUDSDK_AUTH_ACCESS_TOKEN` and a `gcloud auth login --no-launch-browser` first).

Inputs
- Demo survey: Haruna uploads his own 60 to 90 s landscape road clip through https://mend.harunafaruk.com/app (processing takes about 2 minutes). Use that survey in every scene; `/api/runs` lists survey ids.
- Raw clip for the opening shot: `runs/<id>/proxy_m0.mp4` from R2 (`GET /internal/r2/runs/<id>/proxy_m0.mp4` with header `x-mend-key`), or the original in `runs/<id>/inputs/`.

Steps
1. Write the script (timed scenes, about 420 words max) and get Haruna's approval before recording.
2. Record each scene from the live site with Playwright at 1920x1080 (`recordVideo`), scripted clicks, slow readable cursor moves. Launch Chromium with `proxy: { server: process.env.HTTPS_PROXY }` and args `--use-angle=swiftshader --enable-unsafe-swiftshader`, otherwise the map is blank. For the processing scene use Review → "Replay processing" at 4x on the finished survey (real logged events, sped up).
3. Voiceover per scene with Gemini text-to-speech (check the current TTS model name and voices in Google's docs). Measure each clip and fit scene lengths to it.
4. Edit with Remotion in a `video/` folder: title card, scene recordings, captions timed to the voice, zooms on SAM masks, lower thirds ("SAM 3.1 tracking", "Muse Spark review", "Muse Voice Transcribe"), end card with https://mend.harunafaruk.com and the repo URL. Music optional, royalty-free only, quiet under the voice.
5. Render the MP4; check it is under 3:00, audio is clear, captions readable.
6. Deliver: upload to R2 key `downloads/mend-demo.mp4` (`PUT https://mend.harunafaruk.com/internal/r2/downloads/mend-demo.mp4` with header `x-mend-key`). Download link: https://mend.harunafaruk.com/download/mend-demo.mp4. Keep large render files out of git.
7. Draft the submission form answers in `docs/submission.md` in Haruna's voice: plain sentences, no em dashes.
