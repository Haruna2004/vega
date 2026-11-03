"""Settings, paths and static config (concepts, unit rates, prompts)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

try:  # optional .env support for local runs
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env", override=False)
except Exception:  # pragma: no cover
    pass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    return float(value) if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value is not None else default


@dataclass
class Settings:
    api_key: str | None
    base_url: str
    asr_url: str
    spark_model: str
    spark_fast_model: str
    sam_model: str
    asr_model: str
    offline: bool
    data_dir: Path
    config_dir: Path
    proxy_fps: float
    proxy_height: int
    chunk_seconds: float
    chunk_overlap_frames: int
    triage_every_s: float
    sample_fps: float
    max_sam_calls: int
    sam_min_track_frames: int
    sam_min_confidence: float
    geocoder: str
    nominatim_url: str
    overpass_url: str
    user_agent: str
    http_timeout: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(_env("MEND_DATA_DIR", str(REPO_ROOT / "data"))).resolve()
    return Settings(
        api_key=_env("META_MODEL_API_KEY") or _env("MODEL_API_KEY"),
        base_url=_env("META_BASE_URL", "https://api.meta.ai/v1"),
        asr_url=_env("META_ASR_URL", "wss://api.meta.ai/v1/asr/realtime"),
        spark_model=_env("MEND_SPARK_MODEL", "muse-spark-1.3"),
        spark_fast_model=_env("MEND_SPARK_FAST_MODEL", "muse-spark-1.3"),
        sam_model=_env("MEND_SAM_MODEL", "sam-3.1"),
        asr_model=_env("MEND_ASR_MODEL", "muse-voice-transcribe-1.0"),
        offline=_env_bool("MEND_OFFLINE", False),
        data_dir=data_dir,
        config_dir=Path(_env("MEND_CONFIG_DIR", str(REPO_ROOT / "config"))).resolve(),
        proxy_fps=_env_float("MEND_PROXY_FPS", 15.0),
        proxy_height=_env_int("MEND_PROXY_HEIGHT", 720),
        chunk_seconds=_env_float("MEND_CHUNK_SECONDS", 20.0),
        chunk_overlap_frames=_env_int("MEND_CHUNK_OVERLAP_FRAMES", 4),
        triage_every_s=_env_float("MEND_TRIAGE_EVERY_S", 2.0),
        sample_fps=_env_float("MEND_SAMPLE_FPS", 2.0),
        max_sam_calls=_env_int("MEND_MAX_SAM_CALLS", 120),
        sam_min_track_frames=_env_int("MEND_SAM_MIN_TRACK_FRAMES", 3),
        sam_min_confidence=_env_float("MEND_SAM_MIN_CONFIDENCE", 0.35),
        geocoder=_env("MEND_GEOCODER", "nominatim"),
        nominatim_url=_env("MEND_NOMINATIM_URL", "https://nominatim.openstreetmap.org"),
        overpass_url=_env("MEND_OVERPASS_URL", "https://overpass-api.de/api/interpreter"),
        user_agent=_env("MEND_USER_AGENT", "MEND-road-auditor/0.1 (hackathon demo)"),
        http_timeout=_env_float("MEND_HTTP_TIMEOUT", 300.0),
    )


def reset_settings() -> None:
    get_settings.cache_clear()
    load_concepts.cache_clear()


@lru_cache(maxsize=1)
def load_concepts() -> dict[str, Any]:
    path = get_settings().config_dir / "concepts.yaml"
    return yaml.safe_load(path.read_text())


def concept(concept_id: str) -> dict[str, Any]:
    concepts = load_concepts()["concepts"]
    if concept_id not in concepts:
        return {
            "label": concept_id.replace("_", " ").title(),
            "sam_prompt": concept_id.replace("_", " "),
            "color": "#94A3B8",
            "specificity": 1,
            "base_severity": 2,
            "treatment": "debris_removal",
            "quantity": "count",
        }
    return concepts[concept_id]


def concept_ids() -> list[str]:
    return list(load_concepts()["concepts"].keys())


def baseline_concepts() -> list[str]:
    return [cid for cid, c in load_concepts()["concepts"].items() if c.get("baseline")]


def load_unit_rates(path: Path | None = None) -> dict[str, Any]:
    path = path or (get_settings().config_dir / "unit_rates.yaml")
    return yaml.safe_load(path.read_text())


def prompt_template(name: str) -> str:
    return (get_settings().config_dir / "prompts" / f"{name}.md").read_text()
