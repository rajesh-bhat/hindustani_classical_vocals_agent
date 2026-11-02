# CLAUDE.md

Raaga Guru: a voice and text agent (Gemini) that teaches Hindustani classical raaga theory,
grounded in a curated markdown knowledge base.

## Commands

```bash
uv sync                                   # install
uv run python api.py                      # run server → http://localhost:8002
uv run pytest                             # offline retrieval evals (no API key)
uv run python evals/run_agent_evals.py    # end-to-end agent evals (needs GOOGLE_API_KEY)
uv run ruff check . && uv run ruff format --check evals tools
```

## Architecture: who / how / what

| Concern | Lives in | Rule |
|---------|----------|------|
| **Who** the guru is | `prompts/persona.yml` | No procedure, no musical facts |
| **How** it answers | `skills/answering-raaga-questions/SKILL.md` | Procedure only. No raaga facts. |
| **What** it knows | `knowledge/` | Facts only, reached only through the lookup tools |

`config.build_system_prompt()` = persona + SKILL.md body. Don't duplicate procedure in the persona,
and don't put facts (thaats, aaroh, etc.) in either.

Request flow: `static/` ⇄ `api.py` ⇄ `agents/session.py` ⇄ Gemini → `tools/raaga_lookup.py`
(Gemini tool wiring) → `tools/knowledge_base.py` (name resolution, file reads) → `knowledge/`.

## Conventions

- **Never load the wrong raaga.** Name resolution in `tools/knowledge_base.py` is strict on
  purpose: exact name → `RAAGA_ALIASES` → unique leading-word prefix. Don't add substring or
  fuzzy matching. Many raaga names contain another's ("Yaman Kalyan", "Bageshree" ⊃ "shree").
  If a common spelling misses, add an alias plus a case in `evals/test_retrieval.py`.
- **Adding a raaga:** create `knowledge/raagas/<snake_case>.md` with Thaat, Jaati, Vadi, Samvadi,
  Time, Aaroh, Avaroh, Pakad, Chalan Rules and Similar Raagas. Add it to the "Detailed Raaga Files
  Available" list in `raagas/index.md`, and add a source row in `knowledge/REFERENCES.md`.
  `uv run pytest` checks the fields and the index.
- **Skill format:** follow the Agent Skills spec. `name` matches the directory (lowercase-hyphen,
  ≤ 64 chars), `description` ≤ 1024 chars says what and when, and `metadata` values are strings.
  The tests enforce this.
- **Tool payloads** (`raaga`, `details`, `matched_as`, `error`) are read by the model and the
  UI (`static/script.js` `TOOL_LABELS`). Keep them stable.
- Restart the server after changing the persona, the skill or `config.py`. The prompt is built
  at import time.
