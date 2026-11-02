# Voice Session Testing (Raaga Guru)

This document outlines the testing methodology for the Gemini Live API backend (`api.py`) and the progressive disclosure tool pipeline (`tools/raaga_lookup.py`, `tools/knowledge_base.py`).

Because the agent is designed for interactive voice, standard unit tests aren't sufficient. We must verify that the model correctly intercepts user speech, fires the correct backend python tools, and synthesizes accurate responses without hallucinating.

## Evals

Two eval suites live in `evals/`:

### 1. Retrieval evals (offline, deterministic) — `evals/test_retrieval.py`
No API key needed. Verifies the **right raaga file is loaded** and that it carries the **right facts**:
- **Name → file resolution**: prefixes ("Raag Yaman"), informal names ("Darbari" → `darbari_kanada`),
  aliases ("Bhoop" → `bhupali`), and near-neighbours that must not collide ("Todi" ≠ `miyan_ki_todi`,
  "Puriya" ≠ `puriya_dhanashri`, "Kalyan" ≠ `yaman`).
- **Clean misses**: unknown or index-only raagas return an error, never another raaga's file.
- **Facts**: thaat / vadi / samvadi / time / aaroh for key raagas; Malkauns aaroh has no Re/Pa;
  Yaman aaroh skips Pa; fundamentals list all 10 thaats.
- **No wrong-raaga loads**: every raaga name in the index loads its own file or nothing — never
  another raaga's (e.g. "Yaman Kalyan" must not load `yaman.md`, "Bageshree" must not load `shree.md`).
- **Integrity**: every raaga file has the required fields and is reachable by its own name; the
  index's "Detailed Raaga Files" list matches the files on disk.
- **Skill spec**: `SKILL.md` frontmatter follows the Agent Skills spec (name matches directory,
  lowercase-hyphen, description ≤ 1024 chars), holds no raaga facts, and is what the system prompt
  is built from.

```bash
uv run pytest -v
```

### 2. Agent evals (end-to-end, needs `GOOGLE_API_KEY`) — `evals/run_agent_evals.py`
Sends each question in `evals/agent_cases.yaml` to the real agent (text mode), then checks
**which knowledge files the agent loaded** (each `lookup_raaga` argument is resolved exactly as
the tool resolves it) and **whether the answer contains the right facts** (regex groups, plus
forbidden patterns that catch hallucinated swaras or wrong-raaga mixups).

```bash
uv run python evals/run_agent_evals.py              # all cases
uv run python evals/run_agent_evals.py -k thaats    # filter by case id
uv run python evals/run_agent_evals.py --repeat 3 -v  # repeat to measure flakiness
```

Add a case by appending to `agent_cases.yaml` — see the field reference at the top of that file.

## Manual Smoke Test

`scripts/ws_smoke_test.py` streams audio-simulating WebSocket frames directly to the backend exactly as the browser client would. 

To run the full diagnostic test suite:
```bash
uv run python api.py &           # start the server first
uv run python scripts/ws_smoke_test.py
```

### Trace Metrics
The `api.py` backend has been instrumented to forward tool metrics down the WebSocket. The smoke test listens for these signals. When running the script, you should see `[METRIC]` logs proving the agent paused generation to fetch filesystem data:
`[METRIC] Agent Loaded Tool -> lookup_raaga({'raaga_name': 'Yaman'})`

---

## Supported Test Scenarios

The test script automatically runs 5 core scenarios to validate the agent's constraints and logic:

### 1. Robustness & Name Normalization (Fuzzy Matching)
* **Goal:** Verify the agent and tool pipeline can normalize weirdly formatted speech.
* **Test Query:** `"Tell me about Darbari."`
* **Expected Metric:** `[METRIC] Agent Loaded Tool -> lookup_raaga({'raaga_name': 'Darbari Kanada'})`
* **Expected Result:** Successfully identifies the informal name and fetches `darbari_kanada.md`.

### 2. Deep Structural (Chalan) Validation
* **Goal:** Verify the agent rigorously subjects user input to the "Chalan Rules" defined in the markdown files.
* **Test Query:** `"In Raag Yaman, can I sing Sa directly to Pa in the aaroh?"`
* **Expected Metric:** `[METRIC] Agent Loaded Tool -> lookup_raaga({'raaga_name': 'Yaman'})`
* **Expected Result:** The agent correctly forbids it, quoting the rule that "Sa is typically skipped in ascent".

### 3. Dual-Lookup Comparative Logic
* **Goal:** Verify the agent can execute multiple tools in the same turn before speaking.
* **Test Query:** `"What is the difference between Bhupali and Deshkar?"`
* **Expected Metric:** 
  `[METRIC] Agent Loaded Tool -> lookup_raaga({'raaga_name': 'Bhupali'})`
  `[METRIC] Agent Loaded Tool -> lookup_raaga({'raaga_name': 'Deshkar'})`
* **Expected Result:** Contrasts the Vadi notes and performance times from the two structurally identical scales.

### 4. Fundamental Logic (Domain Constraints)
* **Goal:** Verify it uses theoretical fallbacks properly.
* **Test Query:** `"Which are the 10 Hindustani thaats?"`
* **Expected Metric:** `[METRIC] Agent Loaded Tool -> lookup_fundamentals({})`
* **Expected Result:** Returns the correct 10 Bhatkhande thaats.

### 5. Domain Enclosure (Boundary Push)
* **Goal:** Verify the prompt rigorously drops out-of-domain conversations.
* **Test Query:** `"What is the weather like in Mumbai today?"`
* **Expected Metric:** (No tool fired)
* **Expected Result:** Rigidly replies: *"I only help with Hindustani classical music."*

---

> Any changes to the system prompt (`prompts/persona.yml` or `skills/answering-raaga-questions/SKILL.md`) or `config.py` require restarting the WebSocket server before testing:
> `pkill -f "python api.py" && uv run python api.py`
