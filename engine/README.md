# engine/, processing (Python, runs on Google Cloud Run)

Video pipeline: ingest → triage (Muse Spark) → SAM segmentation/tracking →
measure → geo → prioritize → report → render. Reads inputs from and writes
results to R2. Also serves voice notes and the Ask agent.
