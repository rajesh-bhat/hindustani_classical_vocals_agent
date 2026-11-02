"""
tools/raaga_lookup.py
─────────────────────
Raaga knowledge-base lookup tools.

Implements progressive disclosure: the agent calls these tools to fetch
raaga details on demand, rather than loading the entire raaga corpus into context.

The facts live in knowledge/ (settings.knowledge_dir). The procedure for when
and how to call these tools lives in skills/raaga-guru-procedure/SKILL.md.

Three functions are exposed as Gemini function declarations:
  1. lookup_raaga(name)    — loads a specific raaga's detailed structure
  2. list_raagas()         — returns the full index of available raagas
  3. lookup_fundamentals() — loads core Hindustani music theory
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from google.genai import types

from config import settings

logger = logging.getLogger(__name__)


def _knowledge_path(*parts: str) -> str:
    """Build an absolute path under the knowledge base directory."""
    return os.path.join(settings.knowledge_dir, *parts)


def _read_file(path: str) -> str:
    """Read a text file, returning empty string on error."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Knowledge file not found: %s", path)
        return ""
    except Exception:
        logger.exception("Error reading knowledge file: %s", path)
        return ""


def _normalize_name(name: str) -> str:
    """Normalize a raaga name to a filename-safe format.

    Examples:
        'Raag Yaman'       → 'yaman'
        'Darbari Kanada'   → 'darbari_kanada'
        'Miyan ki Todi'    → 'miyan_ki_todi'
        'Puriya Dhanashri' → 'puriya_dhanashri'
    """
    # Strip common prefixes
    name = re.sub(r"(?i)^(raag|raga|raaga)\s+", "", name.strip())
    # Lowercase, replace spaces/hyphens with underscores
    name = re.sub(r"[\s\-]+", "_", name.lower())
    # Remove non-alphanumeric except underscores
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name


# Common colloquial names and spelling variants that map to a different
# canonical filename. Only synonyms the substring fuzzy-matcher below CANNOT
# reach belong here (e.g. "bhoop" shares no substring with "bhupali"); names
# like "darbari" → "darbari_kanada" already resolve via the fuzzy pass.
# Keys and values are in normalized (_normalize_name) form.
_RAAGA_ALIASES = {
    "bhoop": "bhupali",
    "bhoopali": "bhupali",
    "miyan_malhar": "miyan_ki_malhar",
    "mian_malhar": "miyan_ki_malhar",
    "miyan_todi": "miyan_ki_todi",
    "mian_todi": "miyan_ki_todi",
    "hansadhwani": "hansdhwani",
    "hamsadhwani": "hansdhwani",
    "bheempalasi": "bhimpalasi",
    "vrindavani_sarang": "brindavani_sarang",
    "brindabani_sarang": "brindavani_sarang",
}


# ── Tool implementations ─────────────────────────────────────────────────────

async def handle_lookup_raaga(raaga_name: str) -> dict[str, Any]:
    """Look up detailed structure of a specific raaga from the knowledge base."""
    normalized = _normalize_name(raaga_name)
    normalized = _RAAGA_ALIASES.get(normalized, normalized)
    file_path = _knowledge_path("raagas", f"{normalized}.md")

    content = _read_file(file_path)
    if content:
        logger.info("Loaded raaga knowledge file: %s", file_path)
        return {"raaga": raaga_name, "details": content}

    # Try fuzzy: list all files and find closest match
    raagas_dir = _knowledge_path("raagas")
    if os.path.isdir(raagas_dir):
        available = [
            f[:-3] for f in os.listdir(raagas_dir)
            if f.endswith(".md") and f != "index.md"
        ]
        # Simple substring match
        matches = [r for r in available if normalized in r or r in normalized]
        if matches:
            match = matches[0]
            content = _read_file(_knowledge_path("raagas", f"{match}.md"))
            if content:
                return {"raaga": raaga_name, "matched_as": match, "details": content}

        return {
            "raaga": raaga_name,
            "error": f"No detailed file found for '{raaga_name}'. "
                     f"Try checking the index with list_raagas. "
                     f"Available detailed raagas: {', '.join(sorted(available)[:20])}..."
        }

    return {"raaga": raaga_name, "error": "Raaga knowledge directory not found."}


async def handle_list_raagas() -> dict[str, Any]:
    """List all available raagas from the index."""
    index_path = _knowledge_path("raagas", "index.md")
    content = _read_file(index_path)
    if content:
        return {"index": content}
    return {"error": "Raaga index file not found."}


async def handle_lookup_fundamentals() -> dict[str, Any]:
    """Load core Hindustani music theory fundamentals."""
    path = _knowledge_path("raaga_fundamentals.md")
    content = _read_file(path)
    if content:
        return {"fundamentals": content}
    return {"error": "Fundamentals file not found."}


# ── Gemini function declarations ─────────────────────────────────────────────

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="lookup_raaga",
        description=(
            "Look up the detailed structure of a specific Hindustani classical raaga. "
            "Returns: thaat, aaroh, avaroh, pakad, vadi, samvadi, time, mood, chalan rules. "
            "Use when the student asks about a specific raaga's structure, rules, or characteristics."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "raaga_name": types.Schema(
                    type=types.Type.STRING,
                    description="Name of the raaga to look up (e.g., 'Yaman', 'Bhairav', 'Darbari Kanada')"
                )
            },
            required=["raaga_name"],
        ),
    ),
    types.FunctionDeclaration(
        name="list_raagas",
        description=(
            "List all available raagas in the knowledge base with their thaat associations. "
            "Use when the student asks what raagas are available, or wants to browse raagas "
            "by thaat or alphabetically."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={},
        ),
    ),
    types.FunctionDeclaration(
        name="lookup_fundamentals",
        description=(
            "Load core Hindustani classical music theory: saptak, swara system, thaat system, "
            "time theory, vadi/samvadi concepts, jaati classification. "
            "Use when the student asks about general music theory rather than a specific raaga."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={},
        ),
    ),
]

# ── Handler dispatch ─────────────────────────────────────────────────────────

TOOL_HANDLERS: dict[str, Any] = {
    "lookup_raaga": handle_lookup_raaga,
    "list_raagas": handle_list_raagas,
    "lookup_fundamentals": handle_lookup_fundamentals,
}
