"""
Offline retrieval evals — no API key or network needed.

Checks that each raaga name a student (or the model) might use loads the
RIGHT knowledge file, and that the loaded content carries the RIGHT facts.

    uv run pytest evals/test_retrieval.py -v
"""

from __future__ import annotations

import asyncio
import os
import re

import pytest
import yaml

from config import SKILL_PATH, settings
from evals.common import detailed_raaga_files, resolve_file
from tools.knowledge_base import RAAGA_ALIASES, normalize_name
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
    ("Shri", "shree"),
    ("Raag Shri", "shree"),
    ("Bilaval", "bilawal"),
    ("Sri", "shree"),
    ("Bageshree", "bageshri"),  # used to load shree.md ('shree' ⊂ 'bageshree')
    ("Bageshwari", "bageshri"),
    ("Desh", "des"),  # used to load deshkar.md
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


# Distinct raagas whose names contain a covered raaga's name. Each used to load
# the shorter raaga's file (e.g. "Yaman Kalyan" → yaman.md) — a confidently wrong
# answer. They must miss instead.
WRONG_RAAGA_REGRESSIONS = [
    "Yaman Kalyan",
    "Yamani Bilawal",
    "Shuddha Kalyan",
    "Puriya Kalyan",
    "Kamod",
    "Dhanashri",
    "Devashree",
    "Sindhu Bhairavi",
    "Nat Bhairav",
    "Maru Bihag",
    "Des Malhar",
    "Gujari Todi",
    "Bilaskhani Todi",
    "Komal Rishabh Asavari",
    "Hindolam",
]


@pytest.mark.parametrize("name", WRONG_RAAGA_REGRESSIONS)
def test_compound_name_does_not_load_component_raaga(name):
    assert resolve_file(name) is None


def test_partial_name_reports_matched_as():
    result = asyncio.run(handle_lookup_raaga("Darbari"))
    assert result["matched_as"] == "darbari_kanada" and "details" in result


def test_ambiguous_partial_name_misses():
    """'Miyan ki' prefixes both miyan_ki_todi and miyan_ki_malhar — don't guess."""
    assert resolve_file("Miyan ki") is None


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
    """The rule the Yaman chalan agent case relies on must be in the loaded file."""
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


def _index_raaga_names() -> list[str]:
    """Every raaga name listed under a thaat heading in index.md."""
    index = asyncio.run(handle_list_raagas())["index"]
    body = index.split("## Detailed Raaga Files Available", 1)[0]
    names = set()
    for block in body.split("## ")[1:]:
        if "Thaat Raagas" not in block.splitlines()[0]:
            continue
        for line in block.splitlines()[1:]:
            if line and not line.startswith(("Swaras", "-", "#")):
                for raw in line.split(","):
                    name = re.sub(r"\(.*?\)|\*", "", raw).strip()
                    if name:
                        names.add(name)
    return sorted(names)


def test_index_sweep_is_not_empty():
    assert len(_index_raaga_names()) >= 125  # README/skill claim "125+"


@pytest.mark.parametrize("name", _index_raaga_names())
def test_index_name_never_loads_a_different_raaga(name):
    """Every index raaga loads its OWN file or nothing — never another raaga's."""
    stem = resolve_file(name)
    if stem is None:
        return
    own = RAAGA_ALIASES.get(normalize_name(name), normalize_name(name))
    assert stem == own, f"{name!r} loaded {stem}.md"


# ── 5. Skill follows the Agent Skills spec, and is what drives the prompt ─────
SKILL_DIR = os.path.join(os.path.dirname(SKILL_PATH))


def _skill_frontmatter() -> tuple[dict, str]:
    with open(SKILL_PATH, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, flags=re.S)
    assert m, "SKILL.md must start with YAML frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


def test_skill_frontmatter_follows_spec():
    meta, body = _skill_frontmatter()
    name = meta["name"]
    assert name == os.path.basename(SKILL_DIR), "name must match the skill directory"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64
    assert 0 < len(meta["description"]) <= 1024
    assert all(isinstance(v, str) for v in meta.get("metadata", {}).values())
    assert len(body.splitlines()) < 500


def test_skill_contains_no_raaga_facts():
    """Procedure only: no aaroh/avaroh/pakad sequences for any raaga."""
    _, body = _skill_frontmatter()
    assert not re.search(r"\*\*(Aaroh|Avaroh|Pakad|Vadi|Samvadi)\*\*:", body)
    for stem in detailed_raaga_files():
        details = asyncio.run(handle_lookup_raaga(stem))["details"]
        m = re.search(r"\*\*Aaroh\*\*:\s*(.+)", details)
        if m:
            assert m.group(1).strip() not in body


def test_system_prompt_is_persona_plus_skill():
    prompt = settings.live_system_prompt
    _, body = _skill_frontmatter()
    assert body.strip() in prompt
    assert "name: answering-raaga-questions" not in prompt  # frontmatter stripped
    assert "Hindustani Classical Music Guru" in prompt
    assert "I only help with Hindustani classical music." in prompt
