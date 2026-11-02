"""
Central configuration for the Raaga Guru Voice Agent.
All tuneable constants live here — never scatter magic strings across modules.
"""
from __future__ import annotations

import os
import re

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = os.path.dirname(os.path.abspath(__file__))
PERSONA_PATH = os.path.join(_ROOT, "prompts", "persona.yml")
SKILL_PATH = os.path.join(_ROOT, "skills", "answering-raaga-questions", "SKILL.md")


def _strip_frontmatter(markdown: str) -> str:
    """Drop a leading YAML frontmatter block (--- ... ---) from a SKILL.md."""
    match = re.match(r"\A---\s*\n.*?\n---\s*\n", markdown, flags=re.S)
    return markdown[match.end():] if match else markdown


def build_system_prompt() -> str:
    """System prompt = persona (who) + answering skill (how).

    Facts are never in the prompt; the skill tells the model to fetch them from
    knowledge/ with the lookup tools.
    """
    with open(PERSONA_PATH, encoding="utf-8") as f:
        persona = yaml.safe_load(f)["system_instruction"].strip()
    with open(SKILL_PATH, encoding="utf-8") as f:
        procedure = _strip_frontmatter(f.read()).strip()
    return f"{persona}\n\n{procedure}\n"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Google API ────────────────────────────────────────────────────────────
    google_api_key: str = ""

    # ── Gemini Live model (voice mode — real-time audio in/out) ────────────────
    live_model: str = "gemini-3.1-flash-live-preview"

    # ── Gemini text model (text mode — plain generateContent, no audio) ────────
    # Live models are audio-native and reject TEXT-only response modalities, so
    # text mode uses a separate standard model instead of the Live API.
    text_model: str = "gemini-2.5-flash"

    # ── Audio ─────────────────────────────────────────────────────────────────
    audio_input_rate: int = 16_000   # Hz — PCM input from browser microphone
    audio_output_rate: int = 24_000  # Hz — PCM output from Gemini

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8002

    # Maximum simultaneous Live sessions.
    max_concurrent_sessions: int = 10

    # Allowed origins for CORS (comma-separated).
    cors_origins: str = "*"

    # ── Knowledge base path ───────────────────────────────────────────────────
    # Raaga facts (per-raaga files, index, fundamentals, references). The
    # lookup tools read from here. Procedures for *how* to answer live
    # separately under skills/ (see skills/answering-raaga-questions/SKILL.md).
    knowledge_dir: str = os.path.join(_ROOT, "knowledge")

    # ── System prompt (persona + answering skill; shared by voice + text) ─────
    live_system_prompt: str = build_system_prompt()

    def validate_api_key(self) -> None:
        """Raise at startup if the key is missing."""
        if not self.google_api_key:
            raise OSError(
                "GOOGLE_API_KEY is not set. "
                "Add it to your .env file or pass it as an environment variable."
            )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Single shared instance — import this everywhere
settings = Settings()
