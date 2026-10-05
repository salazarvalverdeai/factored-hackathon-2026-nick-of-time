"""Voice input (spec 05 AC-21, lead decision D-072, ADR 0028): `POST /api/voice/transcribe` turns a short clip into text.

The route only transcribes: it returns {text, language} and the web sends that text through the normal chat path, so
the LLM understands and the rules decide exactly as for typed text; it never calls the agent. The clip is the raw
request body (no multipart, so nothing is spooled to a temp file), read into memory under a byte cap and dropped when
the request ends: no disk, no store row, no log of its bytes. The transcript is not logged and never reaches a
notification. Each billed call is one `llm_calls` row (`voice-` trace id) under the daily cap of AC-18.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import os
import re
import uuid
import wave
from array import array
from typing import Callable, Literal, Optional

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.main import ApiError
from nick_of_time import config, llm
from nick_of_time.llm.steps import over_day_cap
from nick_of_time.nlu.rules import detect_language
from nick_of_time.store import Store, StoreError

FORMATS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav"}
MAGIC = {"webm": (0, b"\x1a\x45\xdf\xa3"), "ogg": (0, b"OggS"), "wav": (8, b"WAVE")}
MAX_SECONDS = 30
MAX_BYTES = int(os.getenv("VOICE_MAX_BYTES") or 1_000_000)   # [assumption] 30 s of 16 kHz mono WAV fits; opus is ~10x less
# [data] live smoke 2026-10-05: clips of 1.5-4 s billed 410-426 input tokens (a 30 s audio window plus the prompt)
AUDIO_TOKENS_PER_S, MAX_TOKENS = 15, 400
SILENCE_PEAK = 300                           # [assumption] about -40 dBFS on 16-bit PCM
TIMESTAMPS = re.compile(r"\[\s*\d+m\d+s\d+ms\s*-\s*\d+m\d+s\d+ms\s*\]\s*")   # segment stamps Voxtral may add
READ_TIMEOUT_S = 20
# Customer-facing (spec 07 AC-07 shows them as they are): 503, 413 and 415, in the session language
TYPE_INSTEAD = {"es": "Ahora no podemos escuchar tu audio. Escríbenos tu mensaje y seguimos.",
                "pt": "No momento não conseguimos ouvir seu áudio. Escreva sua mensagem e seguimos."}
TOO_LONG = {"es": "Tu audio es muy largo. Graba hasta 30 segundos o escríbenos tu mensaje.",
            "pt": "Seu áudio está muito longo. Grave até 30 segundos ou escreva sua mensagem."}
UNREADABLE = {"es": "No pudimos leer ese audio. Graba de nuevo o escríbenos tu mensaje.",
              "pt": "Não conseguimos ler esse áudio. Grave de novo ou escreva sua mensagem."}

log = logging.getLogger("nick_of_time.api.voice")


class TranscriptOut(BaseModel):
    text: str
    language: Literal["es", "pt"]


def inspect(audio: bytes, fmt: str) -> tuple[Optional[float], bool]:
    """(seconds, silent). Seconds when the container says it (WAV header, Ogg Opus last granule), else None (WebM from
    MediaRecorder carries no duration: the byte cap bounds it). Silent only for 16-bit WAV whose peak stays under
    SILENCE_PEAK: Voxtral invents sentences for silence (live smoke, 2026-10-05). ValueError: not the declared format."""
    at, magic = MAGIC[fmt]
    if audio[at:at + len(magic)] != magic:
        raise ValueError("not the declared format")
    if fmt == "wav":
        try:
            with wave.open(io.BytesIO(audio)) as w:
                length, width, frames = w.getnframes() / w.getframerate(), w.getsampwidth(), w.readframes(w.getnframes())
        except (wave.Error, EOFError, ZeroDivisionError) as error:
            raise ValueError("unreadable wav") from error
        samples = array("h", frames[:len(frames) // 2 * 2]) if width == 2 else None
        return length, samples is not None and max(map(abs, samples), default=0) < SILENCE_PEAK
    if fmt == "ogg" and b"OpusHead" in audio[:512]:
        last = audio.rfind(b"OggS")
        return int.from_bytes(audio[last + 6:last + 14], "little") / 48_000, False
    return None, False


def default_client() -> llm.LLMClient:
    """Voxtral on Bedrock when `LLM_PROVIDER=bedrock` and the model is priced (D-058); otherwise an unscripted fake,
    whose ProviderUnavailable makes every request a calm 'type instead'."""
    cfg, prices = config.stt()
    if cfg.provider == "bedrock" and prices:
        from nick_of_time.llm.bedrock import BedrockClient
        return BedrockClient(cfg.model, prices=prices, read_timeout_s=READ_TIMEOUT_S, max_attempts=1)
    return llm.FakeClient(cfg.model, prices=prices)


def install(app: FastAPI, store: Store, session: Callable, day_cap: float) -> None:
    app.state.stt = None                    # tests set a scripted FakeClient; else built on first use

    def language(s: dict) -> str:
        return s["language"] if s["language"] in TYPE_INSTEAD else "es"

    def unavailable(s: dict) -> ApiError:
        return ApiError(503, "UNAVAILABLE", TYPE_INSTEAD[language(s)])

    def too_long(s: dict) -> ApiError:
        return ApiError(413, "INVALID", TOO_LONG[language(s)])

    def unreadable(s: dict) -> ApiError:
        return ApiError(415, "INVALID", UNREADABLE[language(s)])

    @app.post("/api/voice/transcribe", response_model=TranscriptOut)
    async def transcribe(request: Request, s: dict = Depends(session)):
        fmt = FORMATS.get(request.headers.get("content-type", "").split(";")[0].strip().lower())
        if fmt is None:
            raise unreadable(s)
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BYTES:
            raise too_long(s)
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_BYTES:
                raise too_long(s)
        audio = bytes(body)
        try:
            length, silent = inspect(audio, fmt)
        except ValueError:
            raise unreadable(s) from None
        if length is not None and length > MAX_SECONDS:
            raise too_long(s)
        if silent:                                          # nothing to hear: no call, no row
            return {"text": "", "language": language(s)}
        client = app.state.stt = app.state.stt or default_client()
        estimate = llm.cost_usd(client.prices, MAX_SECONDS * AUDIO_TOKENS_PER_S + 60, MAX_TOKENS)
        midnight = app.state.now().astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = float(await run_in_threadpool(store.llm_spend_since, midnight))     # store calls off the event loop
        if estimate is None or over_day_cap({"configurable": {"llm_day_spent_usd": spent,
                                                              "llm_day_cap_usd": day_cap}}, estimate):
            raise unavailable(s)
        trace_id = "voice-" + uuid.uuid4().hex[:16]
        try:
            result = await run_in_threadpool(client.transcribe, audio, fmt, max_tokens=MAX_TOKENS)
        except Exception as error:  # noqa: BLE001 — any provider failure: the customer types instead
            (log.info if isinstance(error, llm.ProviderUnavailable) else log.error)(
                "voice transcription failed trace_id=%s error=%s", trace_id, type(error).__name__)
            raise unavailable(s) from None
        try:
            await run_in_threadpool(lambda: store.add_llm_call(
                trace_id=trace_id, provider=result.provider, model=result.model, tokens_in=result.tokens_in,
                tokens_out=result.tokens_out, latency_ms=result.latency_ms, cost_usd=result.cost_usd or 0.0,
                run_id=s["run_id"]))
        except StoreError as error:
            log.error("llm_calls write failed trace_id=%s error=%s", trace_id, error)
        log.info("voice transcribed trace_id=%s format=%s bytes=%d chars=%d", trace_id, fmt, len(audio),
                 len(result.text))
        text = TIMESTAMPS.sub("", result.text).strip()
        return {"text": text, "language": detect_language(text, default=language(s))}
