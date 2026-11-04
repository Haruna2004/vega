# Submission form draft

**Team name:** MEND (change if you registered another name)

**Track:** Indie

**Problem statement:** Build for Your World

**Project description**

MEND turns a single drive down a road into a repair plan a council can act on. You film the road with a phone or a dashcam and upload the video, or use the Capture page on a phone, which logs GPS while you film. A few minutes later you get every pothole outlined and tracked through the video, a size for each one in square metres with an honest range, the damage mapped and grouped into repair sites, those sites ranked by risk to the people who use the road, and work orders, a bill of quantities and a tender document ready to print and sign.

[Add a sentence or two in your own words about why this problem matters to you.] Road repair often starts with someone walking the road with a tape measure. It is hard to know how big the holes are, which ones are dangerous or what fixing them will cost. I wanted something a small works department could run with the phone in their pocket.

Under the hood, Muse Spark looks at sampled frames and plans the scan. SAM 3.1 segments and tracks each defect across the video. A pinhole camera model projects every mask onto the road plane to get real-world area, with the horizon found from SAM's road mask and checked against Muse Spark's own estimate. Muse Spark then reviews the close-up crop of each detection and throws out shadows and puddles. Sites are ranked by severity times exposure, using road class and nearby schools, clinics and bus stops from OpenStreetMap. Inspectors can add a spoken note on site, which Muse Voice Transcribe turns into text and Muse Spark uses to adjust the ranking. Every line in the work orders is tied back to a defect image, and you can ask questions about the survey in plain language and get answers that cite the exact sites and defects.

It is live at https://mend.harunafaruk.com. The engine runs on Google Cloud Run and the app is served from a Cloudflare Worker with R2 storage.

**Public GitHub repo:** https://github.com/Haruna2004/vega

**Demo video:** https://www.youtube.com/watch?v=Khcg06RGetc

**Use of Meta products**

MEND uses three Meta models through the Meta Model API, and each one does a job the product could not do without it. SAM 3.1 is the measuring instrument. It segments potholes and cracks from text prompts and tracks them across video frames, and those masks are what get projected onto the road to produce square metres. It also segments the road itself, which gives the camera calibration its horizon. Muse Spark 1.3 does the judgement work. It triages frames before the expensive segmentation runs, estimates the camera setup, reviews every detection crop to confirm it is a real defect and how bad it is, writes the reasoning behind each site's rank, drafts the tender sections and answers questions about the survey with citations. Muse Voice Transcribe 1.0 turns an inspector's spoken field notes into text, so local knowledge like "kids cross here every morning" changes the repair order.

**Why Meta's models are important**

The hard part of this problem is turning pixels into numbers someone can sign a contract against. SAM 3.1 gives me precise masks that stay locked onto the same pothole as the camera moves, which is what makes measurement and de-duplication possible at all. A box or a label would not be enough to get an area. Muse Spark is strong enough at looking at an image and reasoning about it that it can act as the reviewer a human engineer would otherwise be, and it does it with structured output I can build on. Putting the two together means one person with a phone can produce a measured, ranked survey with the paperwork attached. Every Meta API response is cached by content hash, so re-running a survey costs nothing.

**X post (optional):** add link if you post one.
