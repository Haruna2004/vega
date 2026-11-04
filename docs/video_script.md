# MEND demo video script (target 2:50)

Voice: calm, plain, one narrator. Captions follow the voice. Lower thirds in brackets.

| Time | Screen | Voiceover |
|---|---|---|
| 0:00 to 0:12 | Raw bolonge drive, full screen. Title card "MEND" fades in over it. | Every city has a list of roads to fix. Almost none of them know how big the holes are, which ones are dangerous, or what it will cost. Someone has to walk the road with a tape measure. |
| 0:12 to 0:25 | Landing page, slow scroll. Then `/app`, survey list. | MEND turns one drive into a repair plan. Film the road with a phone or a dashcam, upload it, and a few minutes later you have measured defects, ranked sites and work orders ready to sign. |
| 0:25 to 0:55 | Review, "Replay processing" at 4x. Pipeline steps tick, masks appear on the video, counters climb. [SAM 3.1 tracking] | Muse Spark looks at sampled frames and plans the scan. SAM 3.1 then outlines every pothole and tracks it through the video. A camera model projects each mask onto the road, so every defect gets a size in square metres, with an honest range. |
| 0:55 to 1:20 | Click one clear pothole. Zoom on the mask. Size, range, severity reasons, crop review. [Muse Spark review] | Click any defect to see why it is there. Here is the size, the range, and the reasons behind its severity. Muse Spark reviewed the close-up crop and confirmed it is a real pothole with crumbling edges, not a shadow or a puddle. |
| 1:20 to 1:40 | Map. Road coloured by condition. Ranked sites list. Open site #1. | On the map the road is coloured by condition. Defects close together become repair sites, ranked by risk to people. Severity matters, and so does what is nearby. Schools, clinics and bus stops come from OpenStreetMap. |
| 1:40 to 2:00 | Record a voice note on site #1: "Kids cross here every morning." Transcript appears, rank updates. [Muse Voice Transcribe] | Inspectors know things a camera cannot see. Record a voice note, and Muse Voice Transcribe turns it into text. Muse Spark reads it and adjusts the ranking. This site just moved up. |
| 2:00 to 2:22 | Work orders. Edit a unit rate, total updates. Download the PDF, show it. | Then the paperwork. Work orders and a bill of quantities are built from the measurements. Change a unit rate and every total updates. Download a plain document with signature lines, ready for a contractor. |
| 2:22 to 2:42 | Ask: "What would it cost to fix everything near a school?" Answer appears with site and defect ids. | And you can just ask. Muse Spark answers from the survey itself and cites the exact sites and defects, so every number can be checked. |
| 2:42 to 2:50 | End card: mend.harunafaruk.com, GitHub repo, "Built with Muse Spark, SAM 3.1 and Muse Voice Transcribe". | MEND. One drive, a repair plan you can act on. Built on Meta's models, live today. |

About 400 words.
