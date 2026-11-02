"""
tools/raaga_lookup.py
─────────────────────
Gemini tool wiring for the raaga knowledge base.

Implements progressive disclosure: the agent calls these tools to fetch
raaga details on demand, rather than loading the entire raaga corpus into context.

Three functions are exposed as Gemini function declarations:
  1. lookup_raaga(name)    — loads a specific raaga's detailed structure
  2. list_raagas()         — returns the full index of available raagas
  3. lookup_fundamentals() — loads core Hindustani music theory

File access and name resolution live in knowledge_base.py. The procedure for
when and how the agent calls these tools is the answering-raaga-questions skill
(skills/answering-raaga-questions/SKILL.md), loaded into the system prompt.
"""
from __future__ import annotations

import logging
from typing import Any

from google.genai import types

from tools import knowledge_base as kb

logger = logging.getLogger(__name__)


# ── Tool implementations ─────────────────────────────────────────────────────

async def handle_lookup_raaga(raaga_name: str) -> dict[str, Any]:
    """Look up detailed structure of a specific raaga from the knowledge base."""
    stem, is_partial = kb.resolve_raaga(raaga_name)
    if stem:
        content = kb.read_raaga(stem)
        if content:
            logger.info("Loaded raaga knowledge file: %s.md (asked: %r)", stem, raaga_name)
            result: dict[str, Any] = {"raaga": raaga_name, "details": content}
            if is_partial:
                result["matched_as"] = stem
            return result

    available = kb.available_raagas()
    if not available:
        return {"raaga": raaga_name, "error": "Raaga knowledge directory not found."}

    logger.info("No knowledge file for raaga %r", raaga_name)
    return {
        "raaga": raaga_name,
        "error": f"No detailed file found for '{raaga_name}'. "
                 f"Try checking the index with list_raagas. "
                 f"Available detailed raagas: {', '.join(available[:20])}..."
    }


async def handle_list_raagas() -> dict[str, Any]:
    """List all available raagas from the index."""
    content = kb.read_index()
    if content:
        return {"index": content}
    return {"error": "Raaga index file not found."}


async def handle_lookup_fundamentals() -> dict[str, Any]:
    """Load core Hindustani music theory fundamentals."""
    content = kb.read_fundamentals()
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
