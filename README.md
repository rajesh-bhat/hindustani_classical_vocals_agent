# 🎵 Raaga Guru — Voice AI for Hindustani Classical Music

A real-time AI agent that teaches Hindustani classical music raaga theory. 
Ask about any raaga's structure, swara rules, aaroh-avaroh, pakad, and more — by voice or by text.

## Why a curated knowledge base + procedural skill (not just the model)?

Raaga rules are precise and unforgiving — one wrong swara makes an answer flat wrong, and
LLMs confidently hallucinate aaroh/avaroh, vadi/samvadi, and pakad for all but the most famous
raagas. Instead of trusting the model's memory, Raaga Guru separates **what** it knows from
**how** it answers:

- **Knowledge** (`knowledge/`) — curated raaga facts, loaded on demand by the lookup tools.
- **Skill** (`skills/raaga-guru-procedure/`) — a pure procedure: classify the question, retrieve
  from the knowledge base, ground the answer, reply crisply. It contains no musical facts.

This gives:

- **Accuracy over hallucination** — the model must treat the loaded knowledge file as ground truth
  (never "correct" it from memory), so answers come from curated data, not fuzzy recall.
- **Context efficiency (progressive disclosure)** — the full raaga corpus can't fit in a prompt;
  only the one or two files a question needs are loaded, keeping each request small and focused.
- **Verifiable provenance** — every fact traces to a cited source (Bhatkhande, Tanarang, ITC SRA).
- **Update without retraining** — fix a pakad or add a raaga by editing a markdown file.
- **Consistency & authority** — one coherent interpretation (Bhatkhande system), so the guru
  doesn't contradict itself across sessions.
- **Transparency** — the UI shows a "📚 Loaded knowledge" marker for exactly which file was consulted.

**Tradeoff:** the guru only knows what's in the files (40+ detailed raagas; voice mode falls back
to Google Search, text mode admits the gap). For a teaching tool, bounded-and-correct beats
broad-and-wrong.

## Architecture

```
┌──────────────┐     WebSocket      ┌──────────────┐   voice → Gemini Live    ┌──────────────┐
│   Browser    │ ◄──────────────► │   FastAPI    │ ◄──────────────────► │    Gemini    │
│ Voice / Text │   Audio + JSON    │   api.py     │   text → generateContent  │              │
└──────────────┘                   └──────┬───────┘                        └──────────────┘
                                          │
                                   ┌──────┴───────┐
                                   │ tools/       │
                                   │ raaga_lookup │ ─── knowledge/
                                   │              │       raagas/*.md (40+ files)
                                   └──────────────┘
```

The backend picks the model per mode: **voice** uses the Gemini Live API
(real-time audio), while **text** uses the standard `generateContent` chat API —
Live models are audio-native and can't return text-only responses.

**Key features:**
- **Voice-in / Voice-out**: Speak questions, hear answers
- **Text-only mode**: Type questions and read replies — no mic or speakers needed
- **Progressive disclosure**: 40+ detailed raaga knowledge files loaded on-demand
- **Raaga index**: 140+ raagas organized by thaat, curated from Wikipedia's 1,164-entry list
- **Google Search fallback** (voice mode): For raagas not in the local knowledge base
- **Real-time transcript**: See what you said and what the guru said

## Quick Start

### 1. Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Google API key with Gemini access

### 2. Setup
```bash
# Copy env and add your key
cp .env.example .env
# Edit .env → set GOOGLE_API_KEY=your_key

# Install dependencies
uv sync
```

### 3. Run
```bash
uv run python api.py
```

Open http://localhost:8002 in your browser.

### 4. Talk (or type)
Click **🎙️ Talk to Guru** to speak, or switch to **⌨️ Text** mode to type instead — then ask a question:
- *"Tell me about Raag Yaman"*
- *"What is the difference between Bhupali and Deshkar?"*
- *"Explain the Thaat system"*
- *"What raagas are sung at night?"*

## Skill & Knowledge Files

**Skill = procedure.** [`skills/raaga-guru-procedure/SKILL.md`](skills/raaga-guru-procedure/SKILL.md)
is an [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills) that holds
only the *how*: check scope, classify the question (single raaga / comparison / theory /
browsing), call the right lookup tool(s), handle a miss, ground the answer in the retrieved
payload, and shape a crisp reply. It contains no raaga facts.

**Knowledge = facts.** `knowledge/` is the curated data the tools read, using a
**progressive disclosure** pattern (only the files a question needs are loaded):

| File | Purpose |
|------|---------|
| `raaga_fundamentals.md` | Core theory (swaras, thaats, jaati, time) — `lookup_fundamentals()` |
| `raagas/index.md` | Index of 140+ raagas by thaat (curated from Wikipedia's 1,164-entry list) — `list_raagas()` |
| `raagas/<name>.md` | Detailed structure for 40+ famous raagas — `lookup_raaga(name)` |
| `REFERENCES.md` | Source citations for every file |

Each raaga file includes: Thaat, Jaati, Vadi, Samvadi, Time, Mood, Aaroh, Avaroh, Pakad, Chalan Rules, and Similar Raagas.

## Project Structure

```
.
├── api.py                       # FastAPI app: /ws/live WebSocket bridge, /health, static serving
├── config.py                    # Settings (pydantic) — models, ports, knowledge path; loads the prompt
├── agent_prompt.yml             # Gemini system prompt (shared by voice + text modes)
├── agents/
│   └── live_agent.py            # Gemini session: Live API (voice) + generateContent chat (text)
├── tools/
│   └── raaga_lookup.py          # Tool declarations + handlers; reads knowledge files on demand
├── skills/
│   └── raaga-guru-procedure/
│       └── SKILL.md             # Procedure: scope → classify → retrieve → ground → reply
├── knowledge/                   # Raaga facts (read by the lookup tools)
│   ├── raaga_fundamentals.md    #   Core theory (swaras, thaats, jaati, time)
│   ├── REFERENCES.md            #   Source citations
│   └── raagas/                  #   index.md + 40+ per-raaga files
├── static/                      # Frontend (no build step)
│   ├── index.html               #   Voice/Text UI
│   ├── script.js                #   WebSocket client, audio pipeline, transcript
│   └── style.css                #   Styling
├── test_ws.py                   # WebSocket scenario test client (see TESTING.md)
├── pyproject.toml / uv.lock     # Dependencies
└── .env.example                 # Env template — copy to .env and add GOOGLE_API_KEY
```

**Request flow:** browser (`static/`) ⇄ `api.py` WebSocket ⇄ `agents/live_agent.py` ⇄ Gemini,
with tool calls dispatched to `tools/raaga_lookup.py`, which reads from `knowledge/`.

## Tech Stack

- **Gemini 3.1 Flash Live** — real-time voice + tool calling (voice mode)
- **Gemini 2.5 Flash** — text chat + tool calling (text mode)
- **FastAPI** — WebSocket server  
- **Vanilla JS** — audio capture/playback with Web Audio API
- **Markdown knowledge base + procedural skill** — facts and procedure kept separate

## License

MIT
