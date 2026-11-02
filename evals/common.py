"""Shared helpers for the eval suites."""

from __future__ import annotations

from tools.knowledge_base import available_raagas, resolve_raaga

__all__ = ["detailed_raaga_files", "resolve_file"]


def detailed_raaga_files() -> list[str]:
    """Stems of every per-raaga knowledge file (excluding the index)."""
    return available_raagas()


def resolve_file(raaga_name: str) -> str | None:
    """Which knowledge file does lookup_raaga(raaga_name) load? None on a miss."""
    return resolve_raaga(raaga_name)[0]
