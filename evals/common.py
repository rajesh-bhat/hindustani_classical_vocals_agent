"""Shared helpers for the eval suites."""

from __future__ import annotations

import asyncio
import os

from config import settings
from tools.raaga_lookup import _RAAGA_ALIASES, _normalize_name, handle_lookup_raaga

RAAGAS_DIR = os.path.join(settings.knowledge_dir, "raagas")


def detailed_raaga_files() -> list[str]:
    """Stems of every per-raaga knowledge file (excluding the index)."""
    return sorted(f[:-3] for f in os.listdir(RAAGAS_DIR) if f.endswith(".md") and f != "index.md")


def resolve_file(raaga_name: str) -> str | None:
    """Which knowledge file does lookup_raaga(raaga_name) actually load?

    Returns the file stem (e.g. 'darbari_kanada'), or None if the lookup missed.
    Mirrors the handler's resolution without changing its payload.
    """
    result = asyncio.run(handle_lookup_raaga(raaga_name))
    if "details" not in result:
        return None
    if "matched_as" in result:
        return result["matched_as"]
    normalized = _normalize_name(raaga_name)
    return _RAAGA_ALIASES.get(normalized, normalized)
