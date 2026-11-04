# Writes src/scenes.json from voice durations + recording marks.
import json, os, subprocess
D = {k: v for k, v in ((f[:-4], float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f"public/vo3/{f}"]))) for f in sorted(os.listdir("public/vo3")))}
M = lambda n: json.load(open(f"public/rec/{n}.marks.json")) if os.path.exists(f"public/rec/{n}.marks.json") else {}
Z = json.load(open("scripts/zooms.json")) if os.path.exists("scripts/zooms.json") else {}
lower = {"s3": "SAM 3.1 tracking", "s4": "Muse Spark review", "s5": "Ranked by risk", "s6": "Muse Voice Transcribe", "s8": "Muse Spark answers"}
out = []
for k in ["s1","s2","s3","s4","s5","s6","s7","s8","s9"]:
    sc = {"id": k, "vo": round(D[k], 2)}
    if k == "s1": sc.update(kind="title", clip="rec/raw.mp4", lead=1.5)
    elif k == "s9": sc.update(kind="end")
    else:
        m = M(k); z = Z.get(k, {})
        sc.update(clip=f"rec/{k}.mp4", clipStart=round(m.get(z.get("clipStartMark", "start"), 0) - (1.5 if k == "s6" else 0.3), 2))
    if k in lower: sc["lower"] = lower[k]
    sc.update({a: b for a, b in Z.get(k, {}).items() if a != "clipStartMark"})
    out.append(sc)
json.dump(out, open("src/scenes.json","w"), indent=1)
print(sum(max(s["vo"] + 0.7 + s.get("lead",0), s.get("min",0)) for s in out), "s total")
