# 🎵 Raaga Guru — Voice AI for Hindustani Classical Music

A real-time voice AI agent that teaches Hindustani classical music raaga theory. 
Ask about any raaga's structure, swara rules, aaroh-avaroh, pakad, and more — all through natural voice conversation.

## Why a skills-based knowledge base (not just the model)?

Raaga rules are precise and unforgiving — one wrong swara makes an answer flat wrong, and
LLMs confidently hallucinate aaroh/avaroh, vadi/samvadi, and pakad for all but the most famous
raagas. Instead of trusting the model's memory, Raaga Guru grounds every answer in a curated
knowledge base loaded on demand:

- **Accuracy over hallucination** — the model must treat the loaded skill file as ground truth
  (never "correct" it from memory), so answers come from curated data, not fuzzy recall.
- **Context efficiency (progressive disclosure)** — 1,164 raagas can't fit in a prompt; only the
  one or two files a question needs are loaded, keeping each request small, cheap, and focused.
- **Verifiable provenance** — every fact traces to a cited source (Bhatkhande, Tanarang, ITC SRA).
- **Update without retraining** — fix a pakad or add a raaga by editing a markdown file.
- **Consistency & authority** — one coherent interpretation (Bhatkhande system), so the guru
  doesn't contradict itself across sessions.
- **Transparency** — the UI shows a "📚 Loaded skill" marker for exactly which file was consulted.

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
                                   │ raaga_lookup │ ─── skills/hindustani-raaga-theory/
                                   │              │       raagas/*.md (40+ files)
                                   └──────────────┘
```

The backend picks the model per mode: **voice** uses the Gemini Live API
(real-time audio), while **text** uses the standard `generateContent` chat API —
Live models are audio-native and can't return text-only responses.

**Key features:**
- **Voice-in / Voice-out**: Speak questions, hear answers
- **Text-only mode**: Type questions and read replies — no mic or speakers needed
- **Progressive disclosure**: 30+ detailed raaga skill files loaded on-demand
- **1,164 raaga index**: Complete Wikipedia-sourced Hindustani raaga list
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

## Skill Files

The knowledge base is a self-contained [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills)
(`skills/hindustani-raaga-theory/`) that uses a **progressive disclosure** pattern:

| File | Purpose |
|------|---------|
| `SKILL.md` | Entry point — frontmatter + decision tree for navigation |
| `raaga_fundamentals.md` | Core theory (swaras, thaats, jaati, time) |
| `raagas/index.md` | Full index of 1,164 raagas by thaat |
| `raagas/<name>.md` | Detailed structure for 40+ famous raagas |
| `REFERENCES.md` | Source citations for every file |

Each raaga file includes: Thaat, Jaati, Vadi, Samvadi, Time, Mood, Aaroh, Avaroh, Pakad, Chalan Rules, and Similar Raagas.

## Project Structure

```
.
├── api.py                       # FastAPI app: /ws/live WebSocket bridge, /health, static serving
├── config.py                    # Settings (pydantic) — models, ports, skills path; loads the prompt
├── agent_prompt.yml             # Gemini system prompt (shared by voice + text modes)
├── agents/
│   └── live_agent.py            # Gemini session: Live API (voice) + generateContent chat (text)
├── tools/
│   └── raaga_lookup.py          # Tool declarations + handlers; reads skill files on demand
├── skills/
│   └── hindustani-raaga-theory/ # Self-contained Agent Skill (progressive-disclosure knowledge base)
│       ├── SKILL.md             #   Entry point — frontmatter + decision tree
│       ├── raaga_fundamentals.md  # Core theory (swaras, thaats, jaati, time)
│       ├── REFERENCES.md        #   Source citations
│       └── raagas/              #   index.md + 40+ per-raaga files
├── static/                      # Frontend (no build step)
│   ├── index.html               #   Voice/Text UI
│   ├── script.js                #   WebSocket client, audio pipeline, transcript
│   └── style.css                #   Styling
├── test_ws.py                   # WebSocket scenario test client (see TESTING.md)
├── pyproject.toml / uv.lock     # Dependencies
└── .env.example                 # Env template — copy to .env and add GOOGLE_API_KEY
```

**Request flow:** browser (`static/`) ⇄ `api.py` WebSocket ⇄ `agents/live_agent.py` ⇄ Gemini,
with tool calls dispatched to `tools/raaga_lookup.py`, which reads from `skills/`.

## Tech Stack

- **Gemini 3.1 Flash Live** — real-time voice + tool calling (voice mode)
- **Gemini 2.5 Flash** — text chat + tool calling (text mode)
- **FastAPI** — WebSocket server  
- **Vanilla JS** — audio capture/playback with Web Audio API
- **Progressive skill files** — markdown knowledge base

## License

MIT
