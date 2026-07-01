"""
Central configuration for the Raaga Guru Voice Agent.
All tuneable constants live here — never scatter magic strings across modules.
"""
from __future__ import annotations

import os
import yaml

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Load prompt from YAML ─────────────────────────────────────────────────────
try:
    with open(os.path.join(os.path.dirname(__file__), "agent_prompt.yml"), "r", encoding="utf-8") as _f:
        _prompt_data = yaml.safe_load(_f)
        _system_prompt = _prompt_data.get("system_instruction", "")
except Exception as e:
    print(f"Warning: Failed to load agent prompt from YAML: {e}")
    _system_prompt = "You are a Hindustani Classical Music Guru."



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

    # ── Skill files base path ─────────────────────────────────────────────────
    # Points at the skill folder itself (canonical Agent Skills layout:
    # skills/<skill-name>/SKILL.md + bundled resources).
    skills_dir: str = os.path.join(
        os.path.dirname(__file__), "skills", "hindustani-raaga-theory"
    )

    # ── System prompt ─────────────────────────────────────────────────────────
    live_system_prompt: str = _system_prompt

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
