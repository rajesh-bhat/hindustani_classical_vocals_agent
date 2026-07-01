"""
live_agent.py
─────────────
Manages a single Gemini session for the Raaga Guru — either a bidirectional
Live API voice session, or a plain text chat (Live models are audio-native
and reject TEXT-only response modalities, so text mode uses a separate,
non-Live model instead).

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │  Gemini Live Model  (see config.settings.live_model) │
  │                                                     │
  │  Hears student voice via microphone                 │
  │  Can call tools for raaga knowledge:                │
  │    • lookup_raaga(raaga_name)                       │
  │    • list_raagas()                                  │
  │    • lookup_fundamentals()                          │
  └──────────────────┬──────────────────────────────────┘
                     │ tool_call events (synchronous)
                     ▼
  ┌─────────────────────────────────────────────────────┐
  │  tools/raaga_lookup.py                              │
  │    • Reads skill files from skills/ directory       │
  │    • Progressive disclosure — loads on demand       │
  │    • Returns structured raaga information           │
  └─────────────────────────────────────────────────────┘

Queues:
  receive_q  — caller puts audio/text dicts (or None to stop) here.
  send_q     — this module puts audio/transcript/interrupted dicts here.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import settings
from tools.raaga_lookup import TOOL_DECLARATIONS, TOOL_HANDLERS

logger = logging.getLogger(__name__)

# ── Internal type alias ───────────────────────────────────────────────────────
_Queue = asyncio.Queue[dict[str, Any] | None]


async def run_live_session(
    receive_q: _Queue,
    send_q: _Queue,
    *,
    session_id: str | None = None,
    text_only: bool = False,
) -> None:
    """
    Run a Gemini session and bridge receive_q ↔ send_q.

    Args:
        receive_q: Input queue. Accepted keys per item:
            - ``{"audio": bytes}``          — 16kHz 16-bit mono PCM chunk (voice mode)
            - ``{"text": str}``             — text message
            - ``{"audioStreamEnd": True}``  — mic released; flushes Gemini cache (voice mode)
            - ``None``                      — stop signal (tear down session)
        send_q: Output queue. Produced keys per item:
            - ``{"audio": bytes}``           — 24kHz 16-bit PCM from Gemini (voice mode only)
            - ``{"input_text": str}``        — transcription of user audio (voice mode only)
            - ``{"output_text": str}``       — Gemini's reply text/transcription
            - ``{"interrupted": True}``      — Gemini interrupted; clear playback (voice mode only)
            - ``{"type": "session_closed"}`` — terminal signal
        session_id: Optional correlation ID for log tracing.
        text_only: If True, runs a plain text chat instead of a Live voice session.
    """
    sid = session_id or uuid.uuid4().hex[:8]
    log = logging.LoggerAdapter(logger, {"session_id": sid})

    try:
        settings.validate_api_key()
    except OSError as exc:
        log.error("Cannot start session: %s", exc)
        await send_q.put({"type": "session_closed"})
        return

    client = genai.Client(api_key=settings.google_api_key)

    try:
        if text_only:
            await _run_text_session(client, receive_q, send_q, log)
        else:
            await _run_voice_session(client, receive_q, send_q, log)
    except asyncio.CancelledError:
        log.info("Session cancelled")
    except Exception:
        log.exception("Unexpected error in session")
    finally:
        log.info("Gemini session closed (session_id=%s)", sid)
        await send_q.put({"type": "session_closed"})


# ── Text mode — plain generateContent chat (no audio) ──────────────────────────

async def _run_text_session(
    client: genai.Client,
    receive_q: _Queue,
    send_q: _Queue,
    log: logging.LoggerAdapter,
) -> None:
    """Turn-based text chat with the same raaga tools + Google Search."""
    # Note: the standard generateContent API rejects combining the built-in
    # google_search tool with function declarations in one request, so text
    # mode uses the raaga knowledge tools only (Google Search is voice-only).
    chat = client.aio.chats.create(
        model=settings.text_model,
        config=types.GenerateContentConfig(
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=settings.live_system_prompt)]
            ),
            tools=[
                types.Tool(function_declarations=TOOL_DECLARATIONS),
            ],
        ),
    )

    log.info(
        "Starting text chat model=%s with %d raaga tools",
        settings.text_model,
        len(TOOL_DECLARATIONS),
    )

    while True:
        data: dict[str, Any] | None = await receive_q.get()
        if data is None:
            log.info("Stop signal received; closing text session")
            return

        text = data.get("text")
        if not text:
            continue

        try:
            message: Any = text
            # Resolve tool calls in a loop until Gemini returns a final answer.
            while True:
                response = await chat.send_message(message)
                function_calls = response.function_calls
                if not function_calls:
                    if response.text:
                        await send_q.put({"output_text": response.text})
                    break

                function_response_parts = []
                for fc in function_calls:
                    log.info("Tool call: %s(%s)", fc.name, str(fc.args)[:100])
                    await send_q.put({"debug_tool": fc.name, "debug_args": dict(fc.args)})

                    handler = TOOL_HANDLERS.get(fc.name)
                    if handler:
                        result = await handler(**dict(fc.args))
                    else:
                        result = {"error": f"Tool '{fc.name}' not found."}

                    log.info("Tool %s result: %s", fc.name, str(result)[:200])
                    function_response_parts.append(
                        types.Part.from_function_response(name=fc.name, response=result)
                    )

                message = function_response_parts
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error handling text turn")


# ── Voice mode — bidirectional Live API session ─────────────────────────────────

async def _run_voice_session(
    client: genai.Client,
    receive_q: _Queue,
    send_q: _Queue,
    log: logging.LoggerAdapter,
) -> None:
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=settings.live_system_prompt)]
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                # Wait for 3.5 seconds of absolute silence before considering the turn over
                silence_duration_ms=3500
            )
        ),
        tools=[
            types.Tool(function_declarations=TOOL_DECLARATIONS),
            types.Tool(google_search=types.GoogleSearch()),
        ],
    )

    log.info(
        "Connecting to Gemini Live model=%s with %d raaga tools + Google Search",
        settings.live_model,
        len(TOOL_DECLARATIONS),
    )

    async with client.aio.live.connect(
        model=settings.live_model, config=config
    ) as session:
        log.info("Connected to Gemini Live session")

        # ── Task A: browser → Gemini ──────────────────────────────────────
        async def forward_to_gemini() -> None:
            """Drain receive_q and forward each item to the Gemini session."""
            while True:
                data: dict[str, Any] | None = await receive_q.get()

                if data is None:
                    log.info("Stop signal received; closing forward task")
                    break

                try:
                    if "audio" in data:
                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=data["audio"],
                                mime_type=(
                                    f"audio/pcm;rate={settings.audio_input_rate}"
                                ),
                            )
                        )
                    elif "text" in data:
                        await session.send_realtime_input(text=data["text"])
                    elif data.get("audioStreamEnd"):
                        await session.send_realtime_input(audio_stream_end=True)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Error forwarding data to Gemini (continuing)")

        # ── Task B: Gemini → browser (including tool call handling) ───────
        async def stream_from_gemini() -> None:
            """
            Stream all Gemini responses to send_q across multiple turns.

            Handles three event types:
              1. server_content — audio/transcript/interrupted (normal response)
              2. tool_call      — raaga knowledge lookup; dispatch and respond
              3. Natural loop end — restart to keep listening for next turn
            """
            while True:
                try:
                    async for response in session.receive():

                        # ── 1. Normal model content (audio + transcripts) ──
                        content = response.server_content
                        if content:
                            msg: dict[str, Any] = {}

                            if content.model_turn:
                                for part in content.model_turn.parts:
                                    if part.inline_data:
                                        msg["audio"] = part.inline_data.data

                            if content.input_transcription:
                                msg["input_text"] = content.input_transcription.text
                            if content.output_transcription:
                                msg["output_text"] = content.output_transcription.text
                            if content.interrupted is True:
                                msg["interrupted"] = True

                            if msg:
                                await send_q.put(msg)

                        # ── 2. Tool call — raaga knowledge lookup ──────────
                        tool_call = response.tool_call
                        if tool_call:
                            function_responses: list[types.FunctionResponse] = []

                            for fc in tool_call.function_calls:
                                log.info(
                                    "Tool call: %s(%s)",
                                    fc.name,
                                    str(fc.args)[:100],
                                )
                                # Send debug event to the browser/test-client
                                await send_q.put({
                                    "debug_tool": fc.name,
                                    "debug_args": dict(fc.args)
                                })

                                handler = TOOL_HANDLERS.get(fc.name)
                                if handler:
                                    result = await handler(**dict(fc.args))
                                else:
                                    result = {"error": f"Tool '{fc.name}' not found."}

                                log.info("Tool %s result: %s", fc.name, str(result)[:200])

                                function_responses.append(
                                    types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response=result,
                                    )
                                )

                            await session.send_tool_response(
                                function_responses=function_responses
                            )

                    log.debug("session.receive() turn ended; restarting listener")

                except asyncio.CancelledError:
                    log.info("stream_from_gemini cancelled")
                    return
                except genai_errors.APIError as e:
                    if "1000" in str(e):
                        log.info("Gemini session closed normally")
                        return
                    log.exception("Gemini API error in receive loop")
                    return
                except Exception:
                    log.exception("Fatal error in Gemini receive loop")
                    return

        # ── Supervise both tasks ──────────────────────────────────────────
        forward_task = asyncio.create_task(
            forward_to_gemini(), name="forward_to_gemini"
        )
        stream_task = asyncio.create_task(
            stream_from_gemini(), name="stream_from_gemini"
        )

        done, pending = await asyncio.wait(
            {forward_task, stream_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            exc = task.exception() if not task.cancelled() else None
            if exc:
                log.error("Task '%s' failed: %s", task.get_name(), exc)

        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
