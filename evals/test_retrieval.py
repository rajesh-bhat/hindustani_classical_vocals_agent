"""
Offline retrieval evals — no API key or network needed.

Checks that each raaga name a student (or the model) might use loads the
RIGHT knowledge file, and that the loaded content carries the RIGHT facts.

    uv run pytest evals/test_retrieval.py -v
"""

from __future__ import annotations

import asyncio
import re

import pytest

from evals.common import detailed_raaga_files, resolve_file
from tools.raaga_lookup import (
    handle_list_raagas,
    handle_lookup_fundamentals,
    handle_lookup_raaga,
)

# ── 1. Name → file resolution ────────────────────────────────────────────────
# (name as spoken/typed, expected knowledge file stem)
RESOLUTION_CASES = [
    # exact names, with and without prefixes
    ("Yaman", "yaman"),
    ("Raag Yaman", "yaman"),
    ("raga bhairav", "bhairav"),
    ("Darbari Kanada", "darbari_kanada"),
    ("Miyan ki Todi", "miyan_ki_todi"),
    ("Puriya-Dhanashri", "puriya_dhanashri"),
    # informal / partial names (fuzzy substring pass)
    ("Darbari", "darbari_kanada"),
    ("Brindavani", "brindavani_sarang"),
    # spelling variants (alias table)
    ("Bhoop", "bhupali"),
    ("Bhoopali", "bhupali"),
    ("Hamsadhwani", "hansdhwani"),
    ("Mian Malhar", "miyan_ki_malhar"),
    ("Vrindavani Sarang", "brindavani_sarang"),
    ("Bheempalasi", "bhimpalasi"),
    # near-neighbours that must NOT collide
    ("Todi", "todi"),  # not miyan_ki_todi
    ("Puriya", "puriya"),  # not puriya_dhanashri
    ("Bhairav", "bhairav"),  # not ahir_bhairav / bhairavi
    ("Bhairavi", "bhairavi"),
    ("Ahir Bhairav", "ahir_bhairav"),
    ("Kalyan", "kalyan"),  # not yaman
    ("Malkauns", "malkauns"),  # not chandrakauns
]


@pytest.mark.parametrize(("name", "expected_file"), RESOLUTION_CASES)
def test_name_resolves_to_right_file(name, expected_file):
    assert resolve_file(name) == expected_file


@pytest.mark.parametrize("name", ["Xyzabc", "Raag Nonexistent", "Kirwani"])
def test_unknown_raaga_misses_cleanly(name):
    """Unknown (or index-only) raagas return an error, never another raaga's file."""
    result = asyncio.run(handle_lookup_raaga(name))
    assert "details" not in result
    assert "error" in result and "list_raagas" in result["error"]


# ── 2. Loaded content carries the right facts ────────────────────────────────
# Facts are the ones a student most often asks for; each is a regex matched
# against the field line in the loaded file.
FACT_CASES = [
    (
        "Yaman",
        {"Thaat": r"Kalyan", "Vadi": r"\bGa\b", "Samvadi": r"\bNi\b", "Aaroh": r"'N R G M D N S'"},
    ),
    (
        "Bhupali",
        {"Vadi": r"\bGa\b", "Samvadi": r"\bDha\b", "Time": r"Evening", "Aaroh": r"S R G P D S'"},
    ),
    (
        "Deshkar",
        {"Thaat": r"Bilawal", "Vadi": r"\bDha\b", "Time": r"Morning", "Aaroh": r"S R G P D S'"},
    ),
    ("Darbari", {"Thaat": r"Asavari", "Vadi": r"\bRe\b", "Time": r"Late night"}),
    ("Malkauns", {"Thaat": r"Bhairavi", "Vadi": r"\bMa\b", "Aaroh": r"S g m d n S'"}),
    ("Marwa", {"Vadi": r"\bRe\b", "Aaroh": r"no Pa"}),
    ("Puriya", {"Thaat": r"Marwa", "Vadi": r"\bGa\b", "Samvadi": r"\bNi\b"}),
    ("Bhairav", {"Thaat": r"Bhairav", "Vadi": r"\bDha\b", "Time": r"Morning"}),
]


def _field(details: str, field: str) -> str:
    m = re.search(rf"\*\*{re.escape(field)}\*\*:\s*(.+)", details)
    assert m, f"field {field!r} missing"
    return m.group(1)


@pytest.mark.parametrize(("name", "facts"), FACT_CASES, ids=[c[0] for c in FACT_CASES])
def test_loaded_file_has_right_facts(name, facts):
    details = asyncio.run(handle_lookup_raaga(name))["details"]
    for field, pattern in facts.items():
        assert re.search(pattern, _field(details, field)), f"{name}: {field} != /{pattern}/"


def test_malkauns_aaroh_excludes_re_and_pa():
    """Audav raaga: the loaded aaroh must not contain Re or Pa."""
    details = asyncio.run(handle_lookup_raaga("Malkauns"))["details"]
    aaroh = _field(details, "Aaroh")
    assert not re.search(r"\b[rRP]\b", aaroh)


def test_yaman_aaroh_skips_pa():
    """The rule test_ws.py scenario 2 relies on must be in the loaded file."""
    details = asyncio.run(handle_lookup_raaga("Yaman"))["details"]
    assert "P" not in _field(details, "Aaroh").split("(")[0]
    assert re.search(r"Pa is strictly omitted in the aaroh", details)


# ── 3. Index and fundamentals ────────────────────────────────────────────────
TEN_THAATS = [
    "Bilawal",
    "Kalyan",
    "Khamaj",
    "Bhairav",
    "Purvi",
    "Marwa",
    "Kafi",
    "Asavari",
    "Todi",
    "Bhairavi",
]


def test_fundamentals_lists_all_ten_thaats():
    text = asyncio.run(handle_lookup_fundamentals())["fundamentals"]
    for thaat in TEN_THAATS:
        assert re.search(rf"\|\s*\d+\s*\|\s*{thaat}\s*\|", text), thaat


def test_index_loads():
    index = asyncio.run(handle_list_raagas())["index"]
    assert "Kalyan Thaat" in index and "Yaman" in index


# ── 4. Knowledge base integrity ──────────────────────────────────────────────
REQUIRED_FIELDS = ["Thaat", "Vadi", "Samvadi", "Time", "Aaroh", "Avaroh", "Pakad"]
POINTER_FILES = {"kalyan"}  # intentionally defers to yaman.md for full structure


@pytest.mark.parametrize("stem", [s for s in detailed_raaga_files() if s not in POINTER_FILES])
def test_raaga_file_has_required_fields(stem):
    details = asyncio.run(handle_lookup_raaga(stem))["details"]
    missing = [f for f in REQUIRED_FIELDS if f"**{f}**" not in details]
    assert not missing, f"{stem}.md missing {missing}"


@pytest.mark.parametrize("stem", detailed_raaga_files())
def test_every_file_is_reachable_by_its_own_name(stem):
    assert resolve_file(stem.replace("_", " ").title()) == stem


def test_index_detailed_list_matches_files():
    index = asyncio.run(handle_list_raagas())["index"]
    listed_block = index.split("## Detailed Raaga Files Available", 1)[1]
    listed = {n.strip().lower().replace(" ", "_") for n in listed_block.split("\n\n")[2].split(",")}
    assert set(detailed_raaga_files()) == listed
