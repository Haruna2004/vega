"""Pipeline stages. Each stage reads/writes JSON in data/runs/<run_id>/."""

from __future__ import annotations

from typing import Any

from ..meta_client import get_client

_override: Any = None


def client() -> Any:
    """The Meta client used by every stage (tests swap in a fake)."""
    return _override or get_client()


def set_client(c: Any) -> None:
    global _override
    _override = c
