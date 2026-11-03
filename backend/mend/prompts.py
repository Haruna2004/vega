"""Prompt templates (config/prompts/*.md, Jinja2) and message-part helpers."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from jinja2 import Template

from .config import prompt_template


def render(name: str, **ctx) -> str:
    return Template(prompt_template(name)).render(**ctx).strip()


def image_part(path: str | Path | None = None, *, image=None, max_side: int = 768, quality: int = 80, detail: str | None = None) -> dict:
    """JPEG data-URL image part for Chat Completions, downscaled to save tokens."""
    from PIL import Image

    if image is None:
        image = Image.open(path)
    im = image.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    part: dict = {"type": "image_url", "image_url": {"url": url}}
    if detail:
        part["image_url"]["detail"] = detail
    return part


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}
