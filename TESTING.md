# Voice Session Testing (Raaga Guru)

This document outlines the testing methodology for the Gemini Live API backend (`api.py`) and the progressive disclosure tool pipeline (`tools/raaga_lookup.py`).

Because the agent is designed for interactive voice, standard unit tests aren't sufficient. We must verify that the model correctly intercepts user speech, fires the correct backend python tools, and synthesizes accurate responses without hallucinating.

## Automated Scenario Testing

We use `test_ws.py` to natively stream audio-simulating WebSocket frames directly to the backend exactly as the browser client would. 

To run the full diagnostic test suite:
```bash
uv run python test_ws.py
```

### Trace Metrics
The `api.py` backend has been instrumented to forward tool metrics down the WebSocket. `test_ws.py` listens for these signals. When running the script, you should see `[METRIC]` logs proving the agent paused generation to fetch filesystem data:
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

> Any changes to `agent_prompt.yml` (system prompt), `config.py`, or the `test_ws.py` client require restarting the WebSocket server before testing:
> `pkill -f "python api.py" && uv run python api.py`
