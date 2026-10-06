// Voice helpers for the customer chat (spec 07 AC-10, §8 D-072, ADR 0029). Pure functions: the recorder and the
// speech toggle in app/chat/voice.tsx use them, and lib/voice.test.ts covers them without a browser.

export type Lang = "es" | "pt";

export const MAX_CLIP_SECONDS = 30;
/** Peak level (0..1 RMS) a clip must reach to be sent. Below it the clip is silence: Voxtral invents sentences for
 *  silence, so we never send one. [assumption] */
export const NOISE_FLOOR = 0.02;

/** Calm copy of the page: the fallback when an api error carries no message of its own (the api's 413/415/503 are calm ES/PT). */
export const VOICE_COPY = {
  es: {
    hold: "Mantén para hablar",
    recording: "Grabando… suelta para enviar",
    transcribing: "Transcribiendo…",
    nothing: "No te escuchamos. Inténtalo de nuevo o escribe tu mensaje.",
    tooLong: "El audio es muy largo. Graba un mensaje más corto o escríbelo.",
    badFormat: "No pudimos usar ese audio. Escribe tu mensaje.",
    denied: "No tenemos permiso para usar el micrófono. Actívalo en la configuración del navegador o escribe tu mensaje.",
    offline: "No pudimos conectar. Escribe tu mensaje.",
    draft: "Revisa lo que escuchamos, corrígelo si hace falta y envíalo.",
    readAloud: "Leer respuestas en voz alta",
    online: "usa una voz en línea",
  },
  pt: {
    hold: "Segure para falar",
    recording: "Gravando… solte para enviar",
    transcribing: "Transcrevendo…",
    nothing: "Não ouvimos você. Tente de novo ou escreva sua mensagem.",
    tooLong: "O áudio está muito longo. Grave uma mensagem mais curta ou escreva.",
    badFormat: "Não conseguimos usar esse áudio. Escreva sua mensagem.",
    denied: "Não temos permissão para usar o microfone. Ative nas configurações do navegador ou escreva sua mensagem.",
    offline: "Não conseguimos conectar. Escreva sua mensagem.",
    draft: "Confira o que ouvimos, corrija se precisar e envie.",
    readAloud: "Ler respostas em voz alta",
    online: "usa uma voz on-line",
  },
} as const;

const CANDIDATES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus"] as const;

/** The first recording format the browser supports, in the spec's order, or "wav" for the in-page encoder, or null
 *  when there is no way to record. */
export function pickMime(isTypeSupported: ((t: string) => boolean) | null, canUseAudioContext: boolean): string | null {
  // Bedrock Voxtral accepts WAV only: a webm or ogg opus clip answers 503 (checked on the public URL, 2026-10-05), so
  // the in-page 16 kHz WAV encoder comes first and opus is the last resort.
  if (canUseAudioContext) return "wav";
  if (isTypeSupported) for (const t of CANDIDATES) if (isTypeSupported(t)) return t;
  return null;
}

/** The Content-Type for the POST body: the container only, as the api reads it. */
export function contentTypeOf(mime: string): string {
  return mime === "wav" ? "audio/wav" : mime.split(";")[0];
}

export function isSilent(peak: number): boolean {
  return !(peak >= NOISE_FLOOR);
}

/** Root-mean-square level of a time-domain frame in 0..1 (AnalyserNode.getFloatTimeDomainData). */
export function rms(frame: ArrayLike<number>): number {
  if (frame.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return Math.sqrt(sum / frame.length);
}

/** 16 kHz mono 16-bit PCM WAV from float chunks recorded at `inputRate` (the fallback when MediaRecorder has no opus). */
export function encodeWav16k(chunks: Float32Array[], inputRate: number): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const flat = new Float32Array(total);
  let at = 0;
  for (const c of chunks) {
    flat.set(c, at);
    at += c.length;
  }
  const outRate = 16000;
  const ratio = inputRate / outRate;
  const n = Math.max(0, Math.floor(total / ratio));
  const out = new Uint8Array(44 + n * 2);
  const v = new DataView(out.buffer);
  const tag = (o: number, s: string) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)));
  tag(0, "RIFF");
  v.setUint32(4, 36 + n * 2, true);
  tag(8, "WAVE");
  tag(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, outRate, true);
  v.setUint32(28, outRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  tag(36, "data");
  v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {
    // average the input samples that fall into this output sample (a box filter against aliasing)
    const from = Math.floor(i * ratio);
    const to = Math.max(from + 1, Math.min(total, Math.floor((i + 1) * ratio)));
    let s = 0;
    for (let j = from; j < to; j++) s += flat[j];
    const x = Math.max(-1, Math.min(1, s / (to - from)));
    v.setInt16(44 + i * 2, Math.round(x < 0 ? x * 0x8000 : x * 0x7fff), true);
  }
  return out;
}

export interface VoiceLike {
  lang: string;
  localService: boolean;
  name?: string;
}

// macOS ships novelty voices for every language (Eddy, Flo, Grandma, Rocko…); they read a bank reply as a joke.
const NOVELTY = /\b(eddy|flo|grandma|grandpa|reed|rocko|sandy|shelley|albert|bad news|bahh|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox|fred|junior|kathy|ralph)\b/i;
const NATURAL = /(enhanced|premium|natural|neural|siri|paulina|m[oó]nica|luciana|juan|felipe|francisca)/i;

/** es-MX else any es-*; pt-BR else any pt-*. A local voice beats a network one (the reply text would leave the
 *  device to a speech service otherwise); null when there is none. */
export function pickVoice<T extends VoiceLike>(voices: readonly T[], lang: Lang): T | null {
  const exact = lang === "es" ? "es-mx" : "pt-br";
  const rank = (v: T) => {
    const l = v.lang.toLowerCase().replace("_", "-");
    const fit = l === exact ? 0 : l.startsWith(lang) ? 1 : 9;
    const quality = NOVELTY.test(v.name ?? "") ? 5 : NATURAL.test(v.name ?? "") ? -0.5 : 0;
    return fit + (v.localService ? 0 : 2) + quality;
  };
  const best = [...voices].sort((a, b) => rank(a) - rank(b))[0];
  return best && rank(best) < 9 && !NOVELTY.test(best.name ?? "") ? best : null;
}

/** The text a reply is read as: the reply only (never chips, ids or the trace); markdown marks are dropped. */
export function speakable(text: string): string {
  return text.replace(/[*_`#>]/g, "").replace(/\s+/g, " ").trim();
}

/** True when the only voice for the language is an online one: the reply text would leave the device, so the toggle
 *  says so and read-aloud stays off until the customer turns it on (spec 07 §8.4). */
export function onlineVoiceOnly<T extends VoiceLike>(voices: readonly T[], lang: Lang): boolean {
  const voice = pickVoice(voices, lang);
  return voice !== null && !voice.localService;
}

/** Which calm message an api error becomes (spec 07 AC-10): the api's own ES/PT message for 413, 415 and 503; the
 *  local copy only when that message is empty, or for any other failure. */
export function voiceErrorMessage(status: number, apiMessage: string, lang: Lang): string {
  const own = apiMessage.trim();
  if ((status === 413 || status === 415 || status === 503) && own) return own;
  if (status === 413) return VOICE_COPY[lang].tooLong;
  if (status === 415) return VOICE_COPY[lang].badFormat;
  return VOICE_COPY[lang].offline;
}
