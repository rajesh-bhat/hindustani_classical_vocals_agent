"""
api.py
──────
FastAPI application serving the Raaga Guru Voice Agent.

Endpoints:
  GET  /health          — liveness probe
  WS   /ws/live         — bidirectional Gemini Live bridge (voice in/out)
  GET  /                — serves static/index.html (mounted last)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agents.live_agent import run_live_session
from config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logger = logging.getLogger("raaga_guru.api")

# ── Session limiter ───────────────────────────────────────────────────────────
_session_sem: asyncio.Semaphore | None = None


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Validate config and initialise shared state on startup."""
    global _session_sem

    settings.validate_api_key()
    logger.info(
        "Raaga Guru starting up | model=%s | max_sessions=%d",
        settings.live_model,
        settings.max_concurrent_sessions,
    )

    _session_sem = asyncio.Semaphore(settings.max_concurrent_sessions)

    yield

    logger.info("Raaga Guru shutting down")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Raaga Guru",
    description="Voice AI agent for Hindustani classical music raaga theory",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> JSONResponse:
    """Liveness probe — always returns 200 if the process is alive."""
    return JSONResponse({"status": "ok", "model": settings.live_model})


# ── WebSocket Live Session ────────────────────────────────────────────────────
@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket) -> None:
    """
    Bridge between the browser and the Gemini Live API.

    Query params:
      • mode=text  → Gemini responds with text only (no audio synthesis)

    Protocol (browser → server):
      • Binary frames  → raw 16kHz 16-bit mono PCM audio
      • Text frames    → JSON with one of:
            { "text": "some text message" }
            { "audioStreamEnd": true }

    Protocol (server → browser):
      • Text frames → JSON with one or more of:
            { "audio": "<base64 24kHz PCM>" }   (voice mode only)
            { "input_text": "..." }
            { "output_text": "..." }
            { "interrupted": true }
    """
    assert _session_sem is not None, "Semaphore not initialised"

    # ── Reject if at capacity ─────────────────────────────────────────────────
    if not _session_sem._value:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    text_only = websocket.query_params.get("mode") == "text"

    await websocket.accept()
    sid = uuid.uuid4().hex[:8]
    log = logging.LoggerAdapter(logger, {"session_id": sid})
    log.info("WebSocket accepted (mode=%s)", "text" if text_only else "voice")

    receive_q: asyncio.Queue[dict | None] = asyncio.Queue()
    send_q: asyncio.Queue[dict] = asyncio.Queue()

    # ── Task: browser → receive_q ─────────────────────────────────────────────
    async def receive_from_client() -> None:
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    await receive_q.put({"audio": message["bytes"]})
                elif "text" in message and message["text"]:
                    try:
                        data: dict = json.loads(message["text"])
                    except json.JSONDecodeError:
                        log.warning("Received non-JSON text frame; ignoring")
                        continue

                    if "text" in data:
                        await receive_q.put({"text": data["text"]})
                    elif data.get("audioStreamEnd"):
                        await receive_q.put({"audioStreamEnd": True})

        except WebSocketDisconnect:
            log.info("Client disconnected")
        except RuntimeError:
            log.info("Client disconnected (runtime)")
        except Exception:
            log.exception("Unexpected error in receive_from_client")
        finally:
            await receive_q.put(None)

    # ── Task: send_q → browser ────────────────────────────────────────────────
    async def send_to_client() -> None:
        try:
            while True:
                msg = await send_q.get()
                if msg.get("type") == "session_closed":
                    break

                out: dict = {}
                if "audio" in msg:
                    out["audio"] = base64.b64encode(msg["audio"]).decode()
                if "input_text" in msg:
                    out["input_text"] = msg["input_text"]
                if "output_text" in msg:
                    out["output_text"] = msg["output_text"]
                if "interrupted" in msg:
                    out["interrupted"] = True
                if "debug_tool" in msg:
                    out["debug_tool"] = msg["debug_tool"]
                    out["debug_args"] = msg.get("debug_args", {})

                if out:
                    try:
                        await websocket.send_text(json.dumps(out))
                    except Exception:
                        log.warning("WebSocket send failed; stopping send loop")
                        break

        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Unexpected error in send_to_client")

    # ── Run all three tasks concurrently ──────────────────────────────────────
    async with _session_sem:
        session_task = asyncio.create_task(
            run_live_session(receive_q, send_q, session_id=sid, text_only=text_only)
        )
        rx_task = asyncio.create_task(receive_from_client())
        tx_task = asyncio.create_task(send_to_client())

        _done, pending = await asyncio.wait(
            {rx_task, tx_task, session_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    log.info("WebSocket session closed")


# ── Static files (mounted last so /health and /ws/* take priority) ────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
