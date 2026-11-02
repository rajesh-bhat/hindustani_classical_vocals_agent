"""
tools/knowledge_base.py
───────────────────────
Read-only access to the raaga knowledge base in knowledge/ (settings.knowledge_dir).

Pure Python — no Gemini dependency — so name resolution can be tested directly.
The Gemini tool wiring that exposes this to the model lives in raaga_lookup.py.

Name resolution is deliberately strict. Loading the WRONG raaga's file is worse
than loading none: the model treats the file as ground truth, so a mismatch
becomes a confidently wrong answer. Many raaga names contain other raaga names
("Yaman Kalyan", "Sindhu Bhairavi", "Bageshree" ⊃ "shree"), so raw substring
matching is unsafe. Resolution order:

  1. Exact filename after normalization
  2. Alias table (spelling variants / colloquial names)
  3. Leading-word prefix of exactly ONE filename ("Darbari" → darbari_kanada)
  4. Otherwise: no match
"""

from __future__ import annotations

import logging
import os
import re

from config import settings

logger = logging.getLogger(__name__)

RAAGAS_SUBDIR = "raagas"
INDEX_FILE = "index.md"
FUNDAMENTALS_FILE = "raaga_fundamentals.md"

# Spelling variants and colloquial names → canonical filename stem.
# Keys and values are in normalize_name() form. Add an entry here whenever a
# common name for a covered raaga doesn't resolve (see evals/test_retrieval.py).
RAAGA_ALIASES: dict[str, str] = {
    "bhoop": "bhupali",
    "bhoopali": "bhupali",
    "miyan_malhar": "miyan_ki_malhar",
    "mian_malhar": "miyan_ki_malhar",
    "mian_ki_malhar": "miyan_ki_malhar",
    "miyan_todi": "miyan_ki_todi",
    "mian_todi": "miyan_ki_todi",
    "mian_ki_todi": "miyan_ki_todi",
    "hansadhwani": "hansdhwani",
    "hamsadhwani": "hansdhwani",
    "bheempalasi": "bhimpalasi",
    "vrindavani_sarang": "brindavani_sarang",
    "brindabani_sarang": "brindavani_sarang",
    "shri": "shree",
    "sri": "shree",
    "bilaval": "bilawal",
    "bageshree": "bageshri",
    "bageshwari": "bageshri",
    "desh": "des",
}


def normalize_name(name: str) -> str:
    """Normalize a raaga name to filename form.

    'Raag Yaman' → 'yaman', 'Miyan ki Todi' → 'miyan_ki_todi',
    'Puriya-Dhanashri' → 'puriya_dhanashri'
    """
    name = re.sub(r"(?i)^(raag|raga|raaga)\s+", "", name.strip())
    name = re.sub(r"[\s\-]+", "_", name.lower())
    return re.sub(r"[^a-z0-9_]", "", name)


def _path(*parts: str) -> str:
    return os.path.join(settings.knowledge_dir, *parts)


def _read(path: str) -> str:
    """Read a knowledge file, returning '' if it is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception:
        logger.exception("Error reading knowledge file: %s", path)
        return ""


def available_raagas() -> list[str]:
    """Sorted filename stems of every detailed raaga file."""
    raagas_dir = _path(RAAGAS_SUBDIR)
    if not os.path.isdir(raagas_dir):
        return []
    return sorted(f[:-3] for f in os.listdir(raagas_dir) if f.endswith(".md") and f != INDEX_FILE)


def resolve_raaga(name: str) -> tuple[str | None, bool]:
    """Map a raaga name to a knowledge file stem.

    Returns (stem, is_partial). stem is None when nothing matches safely;
    is_partial is True when the match came from the leading-prefix rule.
    """
    normalized = normalize_name(name)
    if not normalized:
        return None, False
    available = available_raagas()

    candidate = RAAGA_ALIASES.get(normalized, normalized)
    if candidate in available:
        return candidate, False

    prefix = normalized + "_"
    prefix_matches = [stem for stem in available if stem.startswith(prefix)]
    if len(prefix_matches) == 1:
        return prefix_matches[0], True

    return None, False


def read_raaga(stem: str) -> str:
    return _read(_path(RAAGAS_SUBDIR, f"{stem}.md"))


def read_index() -> str:
    return _read(_path(RAAGAS_SUBDIR, INDEX_FILE))


def read_fundamentals() -> str:
    return _read(_path(FUNDAMENTALS_FILE))
