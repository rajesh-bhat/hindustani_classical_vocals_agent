---
name: hindustani-raaga-theory
description: >-
  Comprehensive Hindustani classical music raaga knowledge base covering 1,164
  raagas, with structural details for 40+ of them — aaroh, avaroh, pakad, vadi,
  samvadi, thaat, jaati, time of performance, mood, and chalan rules. Use this
  skill whenever the user asks about any raaga, its swara rules or structure, how
  two raagas differ, or core Hindustani theory such as thaats, saptak, or
  vadi/samvadi — even when they don't say the word "raaga" explicitly.
license: MIT
metadata:
  tags: [music, hindustani, raaga, theory, education, voice, text]
---

# Hindustani Classical Music — Raaga Knowledge Base

## Quick Start

When asked about a specific raaga, call `lookup_raaga(raaga_name)` to load its details.

## Available Knowledge

**Core Theory**: See [raaga_fundamentals.md](raaga_fundamentals.md)
- Saptak, swara system, komal/shuddha/tivra
- 10 Thaats (Bhatkhande classification)
- Time theory (prahar), vadi/samvadi, jaati

**Raaga Index**: See [raagas/index.md](raagas/index.md)
- Full list of 1,164 raagas with thaat associations
- Sourced from Wikipedia's comprehensive Hindustani raaga list

**Detailed Raagas**: See individual files in [raagas/](raagas/)
- 40+ famous raagas with complete structure
- Each file: thaat, aaroh, avaroh, pakad, vadi, samvadi, time, mood, chalan, similar raagas

**Sources & provenance**: See [REFERENCES.md](REFERENCES.md) for the authoritative
sources behind each file — useful when the user questions accuracy or wants citations.

## Decision Tree

1. **Student asks about a specific raaga** → `lookup_raaga("Raag Name")`
2. **Student asks "what raagas exist"** → `list_raagas()`
3. **Student asks about theory concepts** → `lookup_fundamentals()`
4. **Student compares two raagas** → call `lookup_raaga` for BOTH, then explain differences
5. **Raaga not found** → check the index and suggest similar names. In voice mode
   you may also fall back to Google Search; text mode has no search, so rely on the
   index and say so if the raaga isn't covered.
