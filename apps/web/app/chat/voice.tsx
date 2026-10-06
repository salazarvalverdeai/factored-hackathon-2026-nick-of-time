"use client";

// Voice for the customer chat (spec 07 AC-10, §8 D-072, ADR 0029): push-to-talk that fills the composer with an
// editable draft, and read-aloud of agent replies with the browser's speechSynthesis. The clip is never stored. Button
// labels follow the UI locale; the voice and the recorder's notes follow the conversation language (spec 16 AC-06).
import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Volume2, VolumeX } from "lucide-react";
import { useT } from "@/components/i18n-provider";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { useMounted } from "@/lib/use-query";
import { contentTypeOf, encodeWav16k, isSilent, Lang, MAX_CLIP_SECONDS, onlineVoiceOnly, pickMime, pickVoice, rms, speakable, voiceErrorMessage, VOICE_COPY } from "@/lib/voice";

type Phase = "idle" | "recording" | "sending";

const MUTE_KEY = "nick.readAloud"; // "on" when the customer turned read-aloud on; off by default [assumption]

function remembered(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === "on";
  } catch {
    return false; // storage can be blocked: the default is off
  }
}

function canRecord(): boolean {
  return typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) &&
    pickMime(typeof MediaRecorder !== "undefined" ? (t) => MediaRecorder.isTypeSupported(t) : null, typeof AudioContext !== "undefined") !== null;
}

/** Read-aloud state: the toggle (remembered in localStorage when it is available) and `speak`/`cancel`. */
export function useReadAloud(lang: Lang) {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const mounted = useMounted();
  const [choice, setChoice] = useState<boolean | null>(null); // null: nothing chosen yet, so the remembered value
  const on = choice ?? (mounted && remembered());
  // Voices load asynchronously in most browsers: re-check when the list changes (spec 07 §8.4, the online-voice note).
  const [online, setOnline] = useState(false);
  useEffect(() => {
    if (!supported) return;
    const synth = window.speechSynthesis;
    const check = () => setOnline(onlineVoiceOnly(synth.getVoices(), lang));
    check();
    synth.addEventListener?.("voiceschanged", check);
    return () => synth.removeEventListener?.("voiceschanged", check);
  }, [supported, lang]);
  const cancel = useCallback(() => {
    if (supported) window.speechSynthesis.cancel();
  }, [supported]);
  const toggle = useCallback(() => {
    const now = !on;
    setChoice(now);
    try {
      localStorage.setItem(MUTE_KEY, now ? "on" : "off");
    } catch {}
    if (!now) cancel();
  }, [on, cancel]);
  const speak = useCallback(
    (text: string) => {
      if (!supported || !on) return;
      window.speechSynthesis.cancel(); // a new reply cancels the one being spoken
      const u = new SpeechSynthesisUtterance(speakable(text));
      const voice = pickVoice(window.speechSynthesis.getVoices(), lang);
      u.lang = voice?.lang ?? (lang === "es" ? "es-MX" : "pt-BR");
      if (voice) u.voice = voice;
      window.speechSynthesis.speak(u);
    },
    [supported, on, lang],
  );
  useEffect(() => cancel, [cancel]); // leaving the chat stops the voice
  return { supported, on, online, toggle, speak, cancel };
}

/** One fixed label with `aria-pressed` (a screen reader says "pressed" or not); notes an online-only voice. */
export function ReadAloudToggle({ on, online, onToggle }: { on: boolean; online: boolean; onToggle: () => void }) {
  const t = useT();
  return (
    <Button type="button" size="xs" variant="outline" aria-pressed={on} onClick={onToggle}>
      {on ? <Volume2 aria-hidden /> : <VolumeX aria-hidden />}
      {t("chat.voice.readAloud")}
      {online ? <span className="text-muted-foreground">({t("chat.voice.online")})</span> : null}
    </Button>
  );
}

/** Hold to talk (pointer, or Space while focused); a tap toggles for touch users. Releasing sends the clip. */
export function MicButton({
  lang,
  disabled,
  onRecordStart,
  onTranscript,
}: {
  lang: Lang;
  disabled: boolean;
  onRecordStart: () => void;
  onTranscript: (text: string) => void;
}) {
  const t = useT();
  const copy = VOICE_COPY[lang]; // notes in the conversation language, next to the api's own ES/PT messages
  const hold = t("chat.voice.hold");
  const recordingLabel = t("chat.voice.recording");
  const transcribing = t("chat.voice.transcribing");
  const [phase, setPhase] = useState<Phase>("idle");
  const [note, setNote] = useState<string | null>(null);
  const supported = useMounted() && canRecord();
  const run = useRef<{ stop: () => void } | null>(null);
  const downAt = useRef(0);
  const holding = useRef(false);
  // While the permission prompt is open `phase` is still idle: these refs stop a second start and remember a release.
  const starting = useRef(false);
  const stopAsked = useRef(false);

  // release the microphone when the chat goes away
  useEffect(
    () => () => {
      stopAsked.current = true;
      run.current?.stop();
    },
    [],
  );

  async function start() {
    if (starting.current || run.current || phase !== "idle" || disabled) return;
    starting.current = true;
    stopAsked.current = false;
    setNote(null);
    // Created inside the press (before any await) so Safari does not start it suspended; resumed below in any case.
    const ctx = new AudioContext();
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      starting.current = false;
      void ctx.close();
      setNote(copy.denied);
      return;
    }
    await ctx.resume().catch(() => undefined); // a suspended context reads zeros: every clip would look silent
    if (stopAsked.current) {
      // released (Space up, or a hold let go) before the microphone was ready: cancel quietly, nothing is sent
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
      starting.current = false;
      return;
    }
    onRecordStart();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    source.connect(analyser);
    const frame = new Float32Array(analyser.fftSize);
    let peak = 0;
    const meter = setInterval(() => {
      analyser.getFloatTimeDomainData(frame);
      peak = Math.max(peak, rms(frame));
    }, 50);

    const mime = pickMime(typeof MediaRecorder !== "undefined" ? (t) => MediaRecorder.isTypeSupported(t) : null, true)!;
    const parts: BlobPart[] = [];
    const chunks: Float32Array[] = [];
    let recorder: MediaRecorder | null = null;
    let tap: ScriptProcessorNode | null = null;
    if (mime === "wav") {
      // ScriptProcessorNode is deprecated; it stays only as the last fallback (no opus MediaRecorder), without a worklet file.
      tap = ctx.createScriptProcessor(4096, 1, 1); // the in-page encoder for browsers with no opus recorder
      tap.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      source.connect(tap);
      tap.connect(ctx.destination);
    } else {
      recorder = new MediaRecorder(stream, { mimeType: mime });
      recorder.ondataavailable = (e) => e.data.size && parts.push(e.data);
    }
    const limit = setTimeout(() => finish(), MAX_CLIP_SECONDS * 1000);
    let done = false;

    const release = () => {
      clearInterval(meter);
      clearTimeout(limit);
      stream.getTracks().forEach((t) => t.stop()); // the browser's microphone indicator turns off
      tap?.disconnect();
      void ctx.close();
      run.current = null;
    };
    async function upload(clip: Blob) {
      if (isSilent(peak)) {
        setNote(copy.nothing);
        setPhase("idle");
        return;
      }
      try {
        const out = await api.transcribe(clip, contentTypeOf(mime));
        if (out.text.trim()) onTranscript(out.text.trim());
        else setNote(copy.nothing);
      } catch (e) {
        setNote(e instanceof ApiError ? voiceErrorMessage(e.status, e.message, lang) : copy.offline);
      }
      setPhase("idle");
    }
    function finish() {
      if (done) return;
      done = true;
      setPhase("sending");
      if (recorder) {
        recorder.onstop = () => {
          release();
          void upload(new Blob(parts, { type: mime }));
        };
        recorder.stop();
      } else {
        release();
        void upload(new Blob([encodeWav16k(chunks, ctx.sampleRate) as BlobPart], { type: "audio/wav" }));
      }
    }
    run.current = { stop: finish };
    starting.current = false;
    recorder?.start();
    setPhase("recording");
  }

  function stop() {
    if (starting.current) stopAsked.current = true;
    else run.current?.stop();
  }

  if (!supported) return null; // no microphone API: the chat works as typed text

  const recording = phase === "recording";
  return (
    <>
      <Button
        type="button"
        variant={recording ? "default" : "outline"}
        disabled={disabled || phase === "sending"}
        aria-pressed={recording}
        aria-label={hold}
        title={hold}
        onPointerDown={(e) => {
          e.preventDefault();
          holding.current = true;
          downAt.current = Date.now();
          if (starting.current) return; // the permission prompt is still open: a second press starts nothing
          if (phase === "recording") stop();
          else void start();
        }}
        onPointerUp={() => {
          // a long press releases to send; a short tap leaves it recording until the next tap
          if (holding.current && (recording || starting.current) && Date.now() - downAt.current > 400) stop();
          holding.current = false;
        }}
        onKeyDown={(e) => {
          if (e.key === " " && !e.repeat) {
            e.preventDefault();
            if (phase === "idle") void start();
          }
        }}
        onKeyUp={(e) => {
          if (e.key === " ") {
            e.preventDefault();
            stop();
          }
        }}
      >
        <Mic aria-hidden />
        <span className="sr-only sm:not-sr-only">{recording ? recordingLabel : phase === "sending" ? transcribing : hold}</span>
      </Button>
      <span role="status" aria-live="polite" className="sr-only">
        {recording ? recordingLabel : phase === "sending" ? transcribing : (note ?? "")}
      </span>
      {note ? (
        <p lang={lang} className="basis-full text-xs text-muted-foreground">
          {note}
        </p>
      ) : null}
    </>
  );
}
