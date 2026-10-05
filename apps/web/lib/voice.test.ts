import assert from "node:assert/strict";
import { test } from "node:test";
import { contentTypeOf, encodeWav16k, isSilent, pickMime, pickVoice, rms, speakable, voiceErrorMessage, VOICE_COPY } from "./voice.ts";

test("spec 07 AC-07: recording format order is webm/opus, ogg/opus, then in-page WAV", () => {
  assert.equal(pickMime((t) => true, true), "audio/webm;codecs=opus");
  assert.equal(pickMime((t) => t.startsWith("audio/ogg"), true), "audio/ogg;codecs=opus");
  assert.equal(pickMime(() => false, true), "wav");
  assert.equal(pickMime(null, true), "wav");
  assert.equal(pickMime(null, false), null);
  assert.equal(contentTypeOf("audio/webm;codecs=opus"), "audio/webm");
  assert.equal(contentTypeOf("wav"), "audio/wav");
});

test("spec 07 §8 D-072: a clip that never rose above the noise floor is silence", () => {
  assert.equal(isSilent(0), true);
  assert.equal(isSilent(0.005), true);
  assert.equal(isSilent(Number.NaN), true);
  assert.equal(isSilent(0.2), false);
  assert.equal(rms([]), 0);
  assert.ok(Math.abs(rms([1, -1, 1, -1]) - 1) < 1e-9);
});

test("spec 07 §8 D-072: the WAV fallback is 16 kHz mono 16-bit with a valid header", () => {
  const wav = encodeWav16k([new Float32Array(48000).fill(0.5)], 48000); // one second at 48 kHz
  const v = new DataView(wav.buffer);
  assert.equal(String.fromCharCode(...wav.slice(0, 4)), "RIFF");
  assert.equal(String.fromCharCode(...wav.slice(8, 12)), "WAVE");
  assert.equal(v.getUint32(24, true), 16000);
  assert.equal(v.getUint16(22, true), 1);
  assert.equal(v.getUint16(34, true), 16);
  assert.equal(v.getUint32(40, true), 32000); // 16000 samples × 2 bytes
  assert.equal(wav.length, 44 + 32000);
  assert.ok(Math.abs(v.getInt16(44, true) - 16383) < 2);
});

test("spec 07 §8 D-072: read-aloud voice is es-MX else es-*, pt-BR else pt-*, local before network", () => {
  const vs = [
    { lang: "es-ES", localService: true, name: "a" },
    { lang: "es-MX", localService: false, name: "b" },
    { lang: "pt-PT", localService: true, name: "c" },
    { lang: "pt-BR", localService: true, name: "d" },
    { lang: "en-US", localService: true, name: "e" },
  ];
  assert.equal(pickVoice(vs, "es")?.name, "a"); // a local es-ES beats a network es-MX
  assert.equal(pickVoice(vs.filter((v) => v.name !== "a"), "es")?.name, "b");
  assert.equal(pickVoice(vs, "pt")?.name, "d");
  assert.equal(pickVoice(vs.filter((v) => v.lang.startsWith("en")), "es"), null);
});

test("spec 07 §8 D-072: only the reply text is read", () => {
  assert.equal(speakable("**Listo**: bloqueamos\n tu tarjeta."), "Listo: bloqueamos tu tarjeta.");
});

test("spec 07 AC-07: 413 and 415 show calm local copy, 503 the api's message, anything else a generic one", () => {
  assert.equal(voiceErrorMessage(413, "Audio over 1 bytes", "es"), VOICE_COPY.es.tooLong);
  assert.equal(voiceErrorMessage(415, "Send audio/webm", "pt"), VOICE_COPY.pt.badFormat);
  assert.equal(voiceErrorMessage(503, "Ahora no podemos escuchar tu audio.", "es"), "Ahora no podemos escuchar tu audio.");
  assert.equal(voiceErrorMessage(0, "", "pt"), VOICE_COPY.pt.offline);
});
