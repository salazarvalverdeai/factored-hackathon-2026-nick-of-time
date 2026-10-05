"""Spec 05 AC-21 (D-072, ADR 0028): `POST /api/voice/transcribe`. Offline: MemoryStore and the scripted `fake` STT
provider; CI never calls Bedrock (CLAUDE.md)."""
from __future__ import annotations

import io
import logging
import os
import tempfile
import wave
from decimal import Decimal

import pytest

from app import demo, voice
from nick_of_time.config import VOXTRAL_MINI, stt
from nick_of_time.llm import FakeClient, ProviderUnavailable
from tests.test_spec05_api import ME, SECRET, Env

PRICES = {"input_per_1m": 0.04, "output_per_1m": 0.04}      # Voxtral Mini's row of eval/bench/prices.yaml
SAID = "Não reconheço uma compra de 200 reais no meu cartão"
MARK = b"NOT-A-REAL-VOICE-7f3a"                            # marker bytes inside the clip


def wav(secs: float, rate: int = 8000, level: int = 8000) -> bytes:
    """16-bit mono PCM: a square wave of `level` starting with the marker bytes, or pure silence (level 0)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes((MARK if level else bytes(len(MARK))) + (level.to_bytes(2, "little", signed=True) + (-level).to_bytes(2, "little", signed=True))
                      * ((int(secs * rate) * 2 - len(MARK)) // 4))
    return buf.getvalue()


def ogg_opus(secs: float) -> bytes:
    head = b"OggS\x00\x02" + bytes(20) + b"OpusHead" + bytes(11)
    return head + b"OggS\x00\x04" + int(secs * 48_000).to_bytes(8, "little") + bytes(20)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("DAILY_LLM_CAP_USD", raising=False)
    monkeypatch.setattr(demo, "new_run_id", lambda now: None)
    e = Env()
    e.stt = e.app.state.stt = FakeClient(VOXTRAL_MINI, script=[SAID], prices=PRICES)
    return e


def post(env: Env, body: bytes, ctype: str = "audio/wav", client=None):
    return (client or env.client).post("/api/voice/transcribe", content=body, headers={"Content-Type": ctype})


def test_ac_21_a_verified_session_is_required(env):
    assert post(env, wav(1)).status_code == 401                     # no cookie
    r = env.client.post("/api/sessions", json={"customer_id": ME, "mode": "replay"})
    assert r.status_code == 201 and post(env, wav(1)).status_code == 401   # opened, OTP not passed
    assert env.stt.calls == []


@pytest.mark.parametrize("body, ctype, status", [
    (wav(1), "text/plain", 415), (wav(1), "audio/mpeg", 415),
    (b"\x1a\x45\xdf\xa3" + bytes(64), "audio/wav", 415),        # webm bytes declared as wav
    (b"RIFF\x00\x00\x00\x00WAVEjunk", "audio/wav", 415),       # unreadable wav
    (wav(31), "audio/wav", 413), (ogg_opus(31), "audio/ogg", 413)])
def test_ac_21_type_and_duration_limits(env, body, ctype, status):
    env.login()
    r = post(env, body, ctype)
    assert r.status_code == status and r.json()["code"] == "INVALID" and env.stt.calls == []
    assert r.json()["message"] == (voice.TOO_LONG if status == 413 else voice.UNREADABLE)["es"]   # calm, ES/PT


def test_ac_21_limit_messages_follow_the_session_language(env):
    """A pt session gets the Portuguese calm text for 413 and 415, like the 503."""
    r = env.client.post("/api/sessions", json={"customer_id": ME, "mode": "replay", "language": "pt"})
    env.client.post(f"/api/sessions/{r.json()['session_id']}/verify", json={"otp": r.json()["otp_demo"]})
    assert post(env, wav(31)).json()["message"] == voice.TOO_LONG["pt"]
    assert post(env, wav(1), "text/plain").json()["message"] == voice.UNREADABLE["pt"]


def test_ac_21_byte_cap(env, monkeypatch):
    env.login()
    monkeypatch.setattr(voice, "MAX_BYTES", 4_000)
    assert post(env, b"\x1a\x45\xdf\xa3" + bytes(5_000), "audio/webm").status_code == 413
    chunks = iter([b"\x1a\x45\xdf\xa3" + bytes(1_996), bytes(2_000), bytes(2_000)])    # chunked, no Content-Length
    r = env.client.post("/api/voice/transcribe", content=chunks, headers={"Content-Type": "audio/webm"})
    assert r.status_code == 413 and env.stt.calls == []


def test_ac_21_the_llm_calls_row_carries_the_sessions_demo_run(monkeypatch):
    """No new_run_id patch: a public session gets its own demo-… run (ADR 0026), and the voice row is written to it."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    e = Env()
    e.app.state.stt = FakeClient(VOXTRAL_MINI, script=[SAID], prices=PRICES)
    sid = e.login()
    assert post(e, wav(1)).status_code == 200
    run = e.store.get_session(sid).run_id
    assert run.startswith("demo-") and [c.run_id for c in e.store._llm_calls] == [run]


def test_ac_21_fake_stt_returns_text_and_language_and_one_priced_llm_calls_row(env):
    env.login()
    r = post(env, ogg_opus(4), "audio/ogg; codecs=opus")
    assert r.status_code == 200 and r.json() == {"text": SAID, "language": "pt"}
    assert env.stt.calls[0]["format"] == "ogg" and not any(isinstance(v, bytes) for v in env.stt.calls[0].values())
    rows = env.store._llm_calls
    assert len(rows) == 1 and rows[0].trace_id.startswith("voice-") and rows[0].cost_usd > 0
    assert rows[0].provider == "fake" and rows[0].model == VOXTRAL_MINI and rows[0].run_id is None   # the session's run
    env.stt.script.append("Netflix 200")                            # no language evidence: the session's language
    assert post(env, b"\x1a\x45\xdf\xa3" + bytes(64), "audio/webm").json()["language"] == "es"


def test_ac_21_no_audio_or_transcript_is_kept_logged_or_notified(env, caplog):
    env.login()
    before = set(os.listdir(tempfile.gettempdir()))
    with caplog.at_level(logging.DEBUG):
        assert post(env, wav(2)).status_code == 200
    assert set(os.listdir(tempfile.gettempdir())) <= before          # no temp file
    kept = repr(vars(env.store))
    assert MARK.decode() not in kept and SAID not in kept             # the store holds neither the clip nor the text
    assert SAID not in caplog.text and MARK.decode() not in caplog.text
    assert env.notifier.sent == []


def test_ac_21_a_silent_wav_is_not_sent_and_segment_stamps_are_dropped(env):
    """Voxtral invents sentences for silence (live smoke 2026-10-05): a silent 16-bit WAV costs no call."""
    env.login()
    assert post(env, wav(2, level=0)).json() == {"text": "", "language": "es"} and env.stt.calls == []
    env.stt.script[:] = ["[ 0m0s110ms - 0m1s100ms ] Hola, no reconozco un cargo"]
    assert post(env, wav(2)).json() == {"text": "Hola, no reconozco un cargo", "language": "es"}


def test_ac_21_over_the_daily_cap_answers_a_calm_503_and_calls_nothing(env):
    env.login()
    env.store.add_llm_call(trace_id="tr-x", provider="bedrock", model="m", tokens_in=1, tokens_out=1, latency_ms=1,
                           cost_usd=Decimal("5"), run_id=None)
    r = post(env, wav(1))
    assert r.status_code == 503 and r.json()["code"] == "UNAVAILABLE" and "Escríbenos" in r.json()["message"]
    assert env.stt.calls == [] and len(env.store._llm_calls) == 1


def test_ac_21_a_provider_failure_is_a_calm_503_without_a_row(env):
    env.login()
    env.stt.script[:] = [ProviderUnavailable("throttled")]
    r = post(env, wav(1))
    assert r.status_code == 503 and r.json()["policy_id"] is None and env.store._llm_calls == []


def test_ac_21_rate_limited_in_the_turn_bucket(env):
    env.login()
    env.app.state.limiter.limits["turn"] = (1, 100)
    env.stt.script.append(SAID)
    assert post(env, wav(1)).status_code == 200
    assert post(env, wav(1)).status_code == 429 and len(env.stt.calls) == 1


def test_ac_21_stt_defaults_to_voxtral_mini_priced_and_only_bedrock_transcribes():
    cfg, prices = stt({"LLM_PROVIDER": "bedrock"})
    assert cfg.model == VOXTRAL_MINI and prices == PRICES
    assert stt({"BEDROCK_MODEL_STT": "mistral.voxtral-small-24b-2507"})[1] == {"input_per_1m": 0.1,
                                                                              "output_per_1m": 0.3}
    assert stt({"BEDROCK_MODEL_STT": "us.example.unpriced"})[1] is None    # fail closed (D-058)
    with pytest.raises(ProviderUnavailable):
        FakeClient(VOXTRAL_MINI).transcribe(wav(1), "wav")             # unconfigured: 'type instead'


def test_ac_21_bedrock_sends_one_converse_audio_block():
    from nick_of_time.llm.bedrock import BedrockClient

    class Boto:
        def converse(self, **req):
            self.req = req
            return {"output": {"message": {"content": [{"text": " hola "}]}}, "stopReason": "end_turn",
                    "usage": {"inputTokens": 120, "outputTokens": 3}}

    boto = Boto()
    out = BedrockClient(VOXTRAL_MINI, boto_client=boto, prices=PRICES).transcribe(b"RIFF", "wav")
    block = boto.req["messages"][0]["content"]
    assert block[0] == {"audio": {"format": "wav", "source": {"bytes": b"RIFF"}}} and "text" in block[1]
    assert boto.req["inferenceConfig"]["temperature"] == 0 and out.text == "hola" and out.cost_usd > 0
