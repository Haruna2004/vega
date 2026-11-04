import base64, json, os, subprocess, sys, urllib.request, wave
KEY = os.environ["GEMINI_API_KEY"]
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.8-flash-tts"
VOICE = os.environ.get("VOICE", "Charon")
LINES = json.load(open("scripts/lines.json"))
out = {}
for k, text in LINES.items():
    path = f"public/vo/{k}.wav"
    if not os.path.exists(path):
        body = {"contents": [{"parts": [{"text": text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}", data=json.dumps(body).encode(), headers={"content-type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=180))
        part = r["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(part["data"])
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]))
    out[k] = round(d, 2); print(k, out[k], flush=True)
json.dump(out, open("scripts/durations.json", "w"), indent=1)
