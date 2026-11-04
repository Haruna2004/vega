"""Meta Model API client with a content-addressed disk cache.

Every call goes through `_cached()`: the request is normalised (media replaced by
its sha256), hashed, and looked up in `data/cache/<kind>/<hash>.json` before any
network traffic. With `MEND_OFFLINE=1` a cache miss raises `OfflineCacheMiss`
instead of calling the API, so a saved run replays with zero network.

Transports
- Muse Spark: official `openai` SDK (Chat Completions) with `base_url` set.
- SAM 3.1: Responses API over SSE (raw httpx so we keep the exact wire events),
  parsed with Meta's official `meta-sam-parser`.
- Files API: multipart upload for video input (`input_video` + `file_id`).
- Muse Voice Transcribe: realtime WebSocket (`wss://api.meta.ai/v1/asr/realtime`).
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import json
import logging
import mimetypes
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx

from .config import Settings, get_settings

log = logging.getLogger("mend.meta")

# Which run the current call is attributed to (for per-run cost logs).
current_run_dir: contextvars.ContextVar[Path | None] = contextvars.ContextVar("current_run_dir", default=None)

# Placeholder prices per 1M tokens (USD) used only for the cost log estimate.
# The real bill is on the Meta dashboard; edit these if you know better numbers.
PRICE_PER_MTOK = {
    "muse-spark-1.3": (1.0, 4.0),
    "muse-spark-1.3-contributor": (0.5, 2.0),
    "sam-3.1": (1.0, 4.0),
}


class MetaAPIError(RuntimeError):
    pass


class OfflineCacheMiss(MetaAPIError):
    pass


class BudgetExceeded(MetaAPIError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def data_url(path: str | Path, mime: str | None = None) -> str:
    path = Path(path)
    mime = mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def bytes_data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


_DATA_URL_RE = re.compile(r"^data:([^;,]+)?(;base64)?,(.*)$", re.S)


def _normalise_for_key(obj: Any) -> Any:
    """Replace inline media with a digest so cache keys are short and stable."""
    if isinstance(obj, dict):
        return {k: _normalise_for_key(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_normalise_for_key(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 512 and obj.startswith("data:"):
        return "sha256:" + sha256_bytes(obj.encode())
    if isinstance(obj, str) and len(obj) > 4096:
        return "sha256:" + sha256_bytes(obj.encode())
    return obj


def request_key(kind: str, payload: Any) -> str:
    canonical = json.dumps(_normalise_for_key({"kind": kind, "payload": payload}), sort_keys=True, ensure_ascii=False)
    return sha256_bytes(canonical.encode())


class DiskCache:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def path(self, kind: str, key: str) -> Path:
        return self.root / kind / key[:2] / f"{key}.json"

    def get(self, kind: str, key: str) -> dict | None:
        p = self.path(kind, key)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except json.JSONDecodeError:
                log.warning("corrupt cache entry %s", p)
        return None

    def put(self, kind: str, key: str, value: dict) -> None:
        p = self.path(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False))
        tmp.replace(p)


@dataclass
class SamResult:
    prompt: str
    media_kind: str
    raw_text: str
    timeline: list[tuple[float, str]]  # (seconds since request start, delta)
    result: Any  # meta_sam_parser ImageSegmentationResult | VideoSegmentationResult
    usage: dict | None
    cached: bool
    duration_s: float
    events_sample: list[dict] = field(default_factory=list)


def _usage_dict(usage: Any) -> dict | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    try:
        return usage.model_dump()
    except Exception:
        return {"repr": repr(usage)}


def _estimate_cost(model: str, usage: dict | None) -> float:
    if not usage:
        return 0.0
    pin, pout = PRICE_PER_MTOK.get(model, (1.0, 4.0))
    tin = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    tout = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return (tin * pin + tout * pout) / 1_000_000


def _strip_json(text: str) -> Any:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class MetaClient:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.cache = DiskCache(self.s.cache_dir)
        self._openai = None
        self._lock = threading.Lock()
        self.sam_calls_made = 0

    # ------------------------------------------------------------------ utils
    @property
    def offline(self) -> bool:
        return self.s.offline or not self.s.has_key

    def openai(self):
        if self._openai is None:
            from openai import OpenAI

            self._openai = OpenAI(api_key=self.s.api_key, base_url=self.s.base_url, timeout=self.s.http_timeout, max_retries=2)
        return self._openai

    def _log_cost(self, kind: str, model: str, usage: dict | None, cached: bool, extra: dict | None = None) -> None:
        run_dir = current_run_dir.get()
        if run_dir is None:
            return
        entry = {
            "ts": time.time(),
            "kind": kind,
            "model": model,
            "cached": cached,
            "usage": usage,
            "est_cost_usd": 0.0 if cached else round(_estimate_cost(model, usage), 6),
        }
        if extra:
            entry.update(extra)
        with self._lock:
            with open(run_dir / "costs.jsonl", "a") as fh:
                fh.write(json.dumps(entry) + "\n")

    def _miss(self, kind: str, key: str) -> None:
        if self.offline:
            reason = "MEND_OFFLINE=1" if self.s.offline else "no META_MODEL_API_KEY"
            raise OfflineCacheMiss(f"{kind} cache miss ({key[:12]}) and {reason}")

    # ------------------------------------------------------------- Muse Spark
    def spark_chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int | None = None,
        tag: str = "chat",
    ) -> dict:
        """One Chat Completions call. Returns the raw response as a dict."""
        model = model or self.s.spark_model
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"  # the only value Meta accepts
        if response_format:
            payload["response_format"] = response_format
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if max_tokens:
            payload["max_completion_tokens"] = max_tokens
        key = request_key("spark", payload)
        hit = self.cache.get("spark", key)
        if hit is not None:
            self._log_cost(tag, model, hit.get("response", {}).get("usage"), True)
            return hit["response"]
        self._miss("spark", key)
        t0 = time.time()
        resp = self.openai().chat.completions.create(**payload)
        data = resp.model_dump()
        self.cache.put("spark", key, {"kind": "spark", "tag": tag, "created_at": time.time(), "duration_s": time.time() - t0, "request": _normalise_for_key(payload), "response": data})
        self._log_cost(tag, model, data.get("usage"), False)
        return data

    def spark_json(
        self,
        messages: list[dict],
        schema: dict,
        *,
        name: str = "result",
        model: str | None = None,
        reasoning_effort: str | None = None,
        tag: str = "json",
    ) -> dict:
        """Structured output with a strict JSON schema; falls back to json_object mode."""
        fmt = {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}
        try:
            data = self.spark_chat(messages, model=model, response_format=fmt, reasoning_effort=reasoning_effort, tag=tag)
        except OfflineCacheMiss:
            raise
        except Exception as exc:  # schema mode rejected -> instruct + json_object
            log.warning("json_schema mode failed (%s); retrying with json_object", exc)
            hint = {"role": "system", "content": "Reply with one JSON object only, matching this JSON schema:\n" + json.dumps(schema)}
            data = self.spark_chat([hint, *messages], model=model, response_format={"type": "json_object"}, reasoning_effort=reasoning_effort, tag=tag)
        content = data["choices"][0]["message"].get("content") or ""
        return _strip_json(content)

    # ---------------------------------------------------------------- Files
    def upload_file(self, path: str | Path, purpose: str = "user_data") -> str:
        path = Path(path)
        digest = sha256_file(path)
        key = request_key("file", {"sha256": digest, "purpose": purpose, "base_url": self.s.base_url})
        hit = self.cache.get("files", key)
        if hit is not None:
            return hit["id"]
        self._miss("files", key)
        with open(path, "rb") as fh:
            obj = self.openai().files.create(file=(path.name, fh, mimetypes.guess_type(path.name)[0] or "application/octet-stream"), purpose=purpose)
        data = obj.model_dump()
        # Wait for server-side processing if the API reports it.
        for _ in range(60):
            status = data.get("status")
            if status not in ("uploaded", "processing", "pending"):
                break
            time.sleep(2)
            data = self.openai().files.retrieve(data["id"]).model_dump()
        self.cache.put("files", key, {"id": data["id"], "file": data, "path": str(path), "created_at": time.time()})
        return data["id"]

    # --------------------------------------------------------------- SAM 3.1
    def sam_request_body(self, media_kind: str, media_ref: dict, prompt: str, include_confidence: bool = True) -> dict:
        if media_kind == "image":
            media_part = {"type": "input_image", **media_ref}
        else:
            media_part = {"type": "input_video", **media_ref}
        body: dict[str, Any] = {
            "model": self.s.sam_model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}, media_part]}],
            "stream": True,
        }
        if include_confidence:
            body["metadata"] = {"include_confidence": "true"}
        return body

    def sam_segment(
        self,
        media_kind: str,
        media_path: str | Path,
        prompt: str,
        *,
        on_snapshot: Callable[[Any], None] | None = None,
        include_confidence: bool = True,
        tag: str = "sam",
    ) -> SamResult:
        """Text-prompted segmentation of an image or a video file.

        `on_snapshot` receives cumulative meta_sam_parser snapshots as they arrive
        (also when replaying from cache, so the live view behaves the same).
        """
        from meta_sam_parser import CompletedOutcome, IncompleteOutcome, image_segmentation_format, video_segmentation_format

        media_path = Path(media_path)
        digest = sha256_file(media_path)
        key = request_key("sam", {"model": self.s.sam_model, "prompt": prompt, "media_kind": media_kind, "media_sha256": digest, "include_confidence": include_confidence})
        fmt = image_segmentation_format() if media_kind == "image" else video_segmentation_format()
        parser = fmt.create_parser()

        hit = self.cache.get("sam", key)
        if hit is not None:
            for _, delta in hit["timeline"]:
                for snap in parser.push(delta):
                    if on_snapshot:
                        on_snapshot(snap)
            fin = parser.finish(CompletedOutcome() if hit.get("completed", True) else IncompleteOutcome(reason="eof"))
            for snap in fin.events:
                if on_snapshot:
                    on_snapshot(snap)
            self._log_cost(tag, self.s.sam_model, hit.get("usage"), True, {"prompt": prompt})
            return SamResult(prompt, media_kind, hit["raw_text"], [tuple(x) for x in hit["timeline"]], fin.result, hit.get("usage"), True, hit.get("duration_s", 0.0))

        self._miss("sam", key)
        with self._lock:
            if self.sam_calls_made >= self.s.max_sam_calls:
                raise BudgetExceeded(f"MEND_MAX_SAM_CALLS={self.s.max_sam_calls} reached")
            self.sam_calls_made += 1

        if media_kind == "image":
            media_ref = {"image_url": data_url(media_path)}
        else:
            media_ref = {"file_id": self.upload_file(media_path)}
        body = self.sam_request_body(media_kind, media_ref, prompt, include_confidence)

        timeline: list[tuple[float, str]] = []
        events_sample: list[dict] = []
        usage = None
        completed = False
        t0 = time.time()
        headers = {"Authorization": f"Bearer {self.s.api_key}", "Accept": "text/event-stream"}
        with httpx.Client(timeout=httpx.Timeout(self.s.http_timeout, connect=30.0)) as http:
            with http.stream("POST", f"{self.s.base_url}/responses", json=body, headers=headers) as resp:
                if resp.status_code >= 400:
                    raise MetaAPIError(f"SAM {resp.status_code}: {resp.read().decode(errors='replace')[:2000]}")
                for event in _iter_sse(resp.iter_lines()):
                    etype = event.get("type", "")
                    if len(events_sample) < 12 or etype in ("response.completed", "response.failed", "error", "response.incomplete"):
                        events_sample.append(_truncate_event(event))
                    if etype == "response.output_text.delta":
                        delta = event.get("delta", "")
                        timeline.append((round(time.time() - t0, 3), delta))
                        for snap in parser.push(delta):
                            if on_snapshot:
                                on_snapshot(snap)
                    elif etype == "response.completed":
                        completed = True
                        usage = (event.get("response") or {}).get("usage")
                    elif etype in ("response.failed", "error"):
                        raise MetaAPIError(f"SAM stream failed: {json.dumps(event)[:2000]}")
                    elif etype == "response.incomplete":
                        usage = (event.get("response") or {}).get("usage")
        fin = parser.finish(CompletedOutcome() if completed else IncompleteOutcome(reason="eof"))
        for snap in fin.events:
            if on_snapshot:
                on_snapshot(snap)
        raw_text = "".join(d for _, d in timeline)
        duration = time.time() - t0
        self.cache.put(
            "sam",
            key,
            {
                "kind": "sam",
                "prompt": prompt,
                "media_kind": media_kind,
                "media_path": str(media_path),
                "media_sha256": digest,
                "created_at": time.time(),
                "duration_s": duration,
                "completed": completed,
                "usage": usage,
                "request": _normalise_for_key(body),
                "events_sample": events_sample,
                "timeline": timeline,
                "raw_text": raw_text,
            },
        )
        self._log_cost(tag, self.s.sam_model, usage, False, {"prompt": prompt, "duration_s": round(duration, 2)})
        return SamResult(prompt, media_kind, raw_text, timeline, fin.result, usage, False, duration, events_sample)

    # ------------------------------------------------- Muse Voice Transcribe
    def transcribe(self, audio_path: str | Path, *, keywords: list[str] | None = None, language: str = "English") -> dict:
        """Transcribe a short field note. Realtime WebSocket first, Spark audio fallback."""
        audio_path = Path(audio_path)
        pcm = _to_pcm16k(audio_path)
        digest = sha256_bytes(pcm)
        key = request_key("asr", {"model": self.s.asr_model, "pcm_sha256": digest, "keywords": keywords or [], "language": language})
        hit = self.cache.get("asr", key)
        if hit is not None:
            return hit["result"]
        self._miss("asr", key)
        try:
            result = self._transcribe_realtime(pcm, keywords=keywords, language=language)
        except Exception as exc:
            log.warning("realtime ASR failed (%s); falling back to Muse Spark audio input", exc)
            result = self._transcribe_with_spark(pcm)
            result["fallback_reason"] = str(exc)[:500]
        self.cache.put("asr", key, {"kind": "asr", "created_at": time.time(), "result": result})
        self._log_cost("asr", result.get("model", self.s.asr_model), None, False, {"seconds": round(len(pcm) / 32000, 2)})
        return result

    def _transcribe_realtime(self, pcm: bytes, *, keywords: list[str] | None, language: str) -> dict:
        from websockets.sync.client import connect

        url = f"{self.s.asr_url}?sessionId=stream-{uuid.uuid4()}"
        handshake: dict[str, Any] = {
            "authorization": {"accessToken": f"Bearer {self.s.api_key}"},
            "audioEncoding": "PCM_16KHZ",
            "model": self.s.asr_model,
            "mode": "PUSH_TO_TALK",
            "partialMode": "CUMULATIVE",
            "emitAudioProgress": False,
            "languageBias": [language],
        }
        if keywords:
            handshake["keywords"] = keywords
        finals: list[str] = []
        last_partial = ""
        messages: list[dict] = []
        t0 = time.time()
        with connect(url, open_timeout=20, close_timeout=5, max_size=None) as ws:
            ws.send(json.dumps(handshake))
            ack = json.loads(ws.recv(timeout=15))
            messages.append({k: v for k, v in ack.items() if k != "authorization"})
            if "sessionId" not in ack:
                raise MetaAPIError(f"ASR handshake rejected: {ack}")
            step = 3200  # 100 ms of 16 kHz s16 mono
            for i in range(0, len(pcm), step):
                ws.send(pcm[i : i + step])
                time.sleep(0.02)  # ~5x realtime pacing
            ws.send(json.dumps({"type": "endStream"}))
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    raw = ws.recv(timeout=max(0.1, deadline - time.time()))
                except TimeoutError:
                    break
                except Exception:
                    break
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                messages.append(msg)
                mtype = msg.get("type")
                if mtype == "transcript":
                    if msg.get("final"):
                        finals.append(msg.get("transcript", ""))
                        last_partial = ""
                    else:
                        last_partial = msg.get("transcript", "")
                elif mtype == "speechComplete" and msg.get("transcript"):
                    finals.append(msg["transcript"])
                elif mtype == "error":
                    raise MetaAPIError(f"ASR error: {msg}")
        text = " ".join(t.strip() for t in finals if t.strip()) or last_partial.strip()
        return {"text": text, "model": self.s.asr_model, "transport": "realtime-websocket", "duration_s": round(time.time() - t0, 2), "messages": messages[-20:]}

    def _transcribe_with_spark(self, pcm: bytes) -> dict:
        wav = _pcm_to_wav(pcm)
        messages = [
            {"role": "system", "content": "You are a transcription engine. Return only the verbatim transcript of the audio, no commentary."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Transcribe this field note verbatim."},
                    {"type": "input_audio", "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"}},
                ],
            },
        ]
        data = self.spark_chat(messages, tag="asr_fallback", reasoning_effort="low")
        text = (data["choices"][0]["message"].get("content") or "").strip()
        return {"text": text, "model": self.s.spark_model, "transport": "spark-audio-input"}


# ------------------------------------------------------------------ helpers
def _iter_sse(lines: Iterable[str]):
    """Yield JSON payloads from an SSE line stream."""
    buf: list[str] = []
    for line in lines:
        if line == "":
            if buf:
                data = "\n".join(buf)
                buf = []
                if data.strip() == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    log.debug("non-JSON SSE data: %s", data[:200])
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            buf.append(line[5:].lstrip())
    if buf:
        data = "\n".join(buf)
        if data.strip() and data.strip() != "[DONE]":
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                pass


def _truncate_event(event: dict, limit: int = 600) -> dict:
    out = {}
    for k, v in event.items():
        if isinstance(v, str) and len(v) > limit:
            out[k] = v[:limit] + f"...<{len(v)} chars>"
        elif isinstance(v, dict):
            out[k] = _truncate_event(v, limit)
        else:
            out[k] = v
    return out


def _to_pcm16k(path: Path) -> bytes:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
        check=True,
    )
    return proc.stdout


def _pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


_client: MetaClient | None = None


def get_client():
    """THE switch between real Meta models and the simulation (see simulate.py)."""
    global _client
    if _client is None:
        from .simulate import SimulatedMetaClient, provider_name

        _client = SimulatedMetaClient() if provider_name() == "simulate" else MetaClient()
    return _client


def reset_client() -> None:
    global _client
    _client = None
