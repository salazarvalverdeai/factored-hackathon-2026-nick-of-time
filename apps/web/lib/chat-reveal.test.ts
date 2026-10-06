// Offline checks of the paced reveal and the inline "how I decided" line (spec 07 AC-16 to AC-18, AC-22, AC-23).
// Fake timers stand in for the clock; no network, no LLM.
import assert from "node:assert/strict";
import test, { mock } from "node:test";
import { Pacer, STEP_DWELL_MS, type TurnFrame, frameGap, revealMarkdown, stepsSummary, wordCount, wordTokens, wordsAt } from "./chat-reveal.ts";
import { CITE_PREFIX, chipsFor, citeFigures, citeTarget, isPersonChip, primaryChipIndex, type ToolEvent } from "./chat-stream.ts";
import { CHAT_STRINGS } from "./chat-strings.ts";
import { REPLY_PARTS, cardDelay, enter, partDelay } from "./chat-motion.ts";
import type { Suggestion } from "./types.ts";

const AT = "2026-06-01T15:00:00Z";
const tool = (id: string, step: string, status: ToolEvent["status"], cards: ToolEvent["cards"] = []): ToolEvent => ({ id, step, title: step, status, cards, at: AT });

test("spec 07 AC-17: steps are released in order, each result after a minimum dwell (fake timers)", () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 });
  try {
    const released: { at: number; frame: string }[] = [];
    const pacer = new Pacer<TurnFrame<string>>((f) => released.push({ at: Date.now(), frame: f.kind === "tool" ? `${f.event.id}:${f.event.status}` : f.kind }), frameGap);
    // A fast backend: the whole turn arrives at t=0.
    pacer.push({ kind: "tool", event: tool("a", "search_transaction", "running") });
    pacer.push({ kind: "tool", event: tool("a", "search_transaction", "done") });
    pacer.push({ kind: "tool", event: tool("b", "evaluate_policy", "running") });
    pacer.push({ kind: "tool", event: tool("b", "evaluate_policy", "done") });
    pacer.push({ kind: "reply", reply: "ok" });
    assert.deepEqual(released.map((r) => r.frame), ["a:running"], "only the first step shows at once");
    mock.timers.tick(STEP_DWELL_MS - 1);
    assert.equal(released.length, 1, "a step keeps its running state for the whole dwell");
    mock.timers.tick(1);
    assert.deepEqual(released.map((r) => r.frame), ["a:running", "a:done", "b:running"]);
    mock.timers.tick(STEP_DWELL_MS);
    assert.deepEqual(
      released.map((r) => [r.frame, r.at]),
      [
        ["a:running", 0],
        ["a:done", 350],
        ["b:running", 350],
        ["b:done", 700],
        ["reply", 700],
      ],
      "the order never changes; only the pace does",
    );
  } finally {
    mock.timers.reset();
  }
});

test("spec 07 AC-17: a slow backend is not slowed further, and reduced motion releases everything at once", () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 });
  try {
    const got: string[] = [];
    const pacer = new Pacer<TurnFrame<string>>((f) => got.push(f.kind === "tool" ? f.event.status : f.kind), frameGap);
    pacer.push({ kind: "tool", event: tool("a", "block_card", "running") });
    mock.timers.tick(2000); // the real call took 2 s
    pacer.push({ kind: "tool", event: tool("a", "block_card", "done") });
    assert.deepEqual(got, ["running", "done"], "the result shows as soon as it arrives after the dwell");

    const instant: string[] = [];
    const still = new Pacer<TurnFrame<string>>((f) => instant.push(f.kind), frameGap, { instant: true });
    still.push({ kind: "tool", event: tool("x", "open_case", "running") });
    still.push({ kind: "tool", event: tool("x", "open_case", "done") });
    still.push({ kind: "reply", reply: "ok" });
    assert.equal(instant.length, 3, "prefers-reduced-motion: no dwell");

    const cancelled: string[] = [];
    const gone = new Pacer<TurnFrame<string>>((f) => cancelled.push(f.kind), frameGap);
    gone.push({ kind: "tool", event: tool("y", "open_case", "running") });
    gone.push({ kind: "tool", event: tool("y", "open_case", "done") });
    gone.cancel(); // "Nuevo caso" while a turn runs
    mock.timers.tick(5000);
    assert.deepEqual(cancelled, ["tool"], "a cancelled turn releases nothing more");
  } finally {
    mock.timers.reset();
  }
});

test("spec 07 AC-18: the reply is revealed word by word at about 35 words per second", () => {
  assert.equal(wordsAt(0), 0);
  assert.equal(wordsAt(1000), 35);
  assert.equal(wordsAt(100), 3);
  assert.deepEqual(wordTokens("Hola Ana.\n- uno\n2. dos"), ["Hola ", "Ana.\n", "- uno\n", "2. dos"], "a list marker travels with its word");
  assert.equal(wordCount("Listo, Gerardo. Tu caso quedó abierto."), 6);
});

test("spec 07 AC-18: a partly revealed reply never shows half a markdown mark", () => {
  const text = "Tu caso **K-845156** quedó abierto. Revisa [tu caso](/case/K-845156) cuando quieras.";
  assert.equal(revealMarkdown(text, 2), "Tu caso", "an opening ** waits for its pair");
  assert.equal(revealMarkdown(text, 3), "Tu caso **K-845156**");
  assert.equal(revealMarkdown(text, 7), "Tu caso **K-845156** quedó abierto. Revisa", "a link shows only once whole");
  assert.equal(revealMarkdown(text, 8), "Tu caso **K-845156** quedó abierto. Revisa [tu caso](/case/K-845156)");
  assert.equal(revealMarkdown(text, 99), text, "all words: the text as it is");
  assert.equal(revealMarkdown("`V-1` listo", 1), "`V-1`");
  for (let n = 0; n <= wordCount(text); n++) {
    const shown = revealMarkdown(text, n);
    assert.equal((shown.match(/\*\*/g) ?? []).length % 2, 0, `no lone ** at ${n} words`);
    assert.ok(!/\[[^\]]*$/.test(shown), `no open [ at ${n} words`);
  }
});

test("spec 07 AC-16: the collapsed line says what the steps did and how many there were", () => {
  const verified = [{ type: "action" as const, tool: "block_card", state: "verified" as const, verification_id: "V-1" }];
  const tools = [
    tool("1", "search_transaction", "done"),
    tool("2", "evaluate_policy", "done"),
    tool("3", "open_case", "done"),
    tool("4", "get_case", "done"),
  ];
  assert.equal(stepsSummary(tools, "es"), "Revisó tus cargos, aplicó la regla y abrió el caso · 4 pasos");
  assert.equal(stepsSummary(tools, "pt"), "Revisou suas cobranças, aplicou a regra e abriu o caso · 4 etapas");
  const blocked = [tool("1", "search_transaction", "done"), tool("2", "evaluate_policy", "done"), tool("3", "block_card", "done", verified), tool("4", "open_case", "done"), tool("5", "compute_deadline", "done")];
  assert.equal(stepsSummary(blocked, "es"), "Revisó tus cargos, aplicó la regla, bloqueó la tarjeta y abrió el caso · 5 pasos", "at most four phrases, the deadline dropped first");
  const requested = [tool("1", "block_card", "done", [{ type: "action", tool: "block_card", state: "requested", verification_id: null }])];
  assert.equal(stepsSummary(requested, "es"), "Pidió el bloqueo · 1 paso", "constitution #4: requested never reads as blocked");
  assert.equal(stepsSummary([tool("1", "block_card", "failed")], "es"), "Intentó bloquear la tarjeta · 1 paso · 1 no se completó");
  assert.equal(stepsSummary([tool("1", "mystery", "done")], "es"), `${CHAT_STRINGS.howDecided.es} · 1 paso`);
});

test("spec 07 AC-22: a figure a tool returned is cited to that tool, once, outside code and links", () => {
  const tools = [
    tool("tc-1", "search_transaction", "done", [{ type: "charge", transaction_id: "tx-1", date: "2026-05-26", amount: 1366.1, currency: "USD", merchant: null, last4: "6274", synthetic: false }]),
    tool("tc-2", "open_case", "done", [{ type: "case", case_id: "K-845156", status: "new" }]),
    tool("tc-3", "compute_deadline", "running"),
  ];
  const out = citeFigures("El cargo de 1,366.10 USD. Tu caso **K-845156** quedó abierto; caso K-845156. [ver](/case/K-845156) `K-845156` y 999.00 USD.", tools, "es");
  assert.match(out, /\[1,366\.10 USD\]\(#cite-tc-1\)/);
  assert.match(out, /\*\*\[K-845156\]\(#cite-tc-2\)\*\*/);
  assert.equal(out.match(/#cite-tc-2/g)?.length, 1, "cited once");
  assert.match(out, /\[ver\]\(\/case\/K-845156\) `K-845156`/, "links and code are left alone");
  assert.match(out, / 999\.00 USD\.$/, "a figure no tool returned is not cited");
  assert.equal(citeTarget(`${CITE_PREFIX}tc-2`), "tc-2");
  assert.equal(citeTarget("/case/K-1"), null);
});

test("spec 07 AC-27: under reduced motion no element gets animated props; otherwise short ease-out entrances", () => {
  for (const kind of ["user", "agent", "part", "card", "receipt", "seal", "chips", "fade"] as const) {
    assert.deepEqual(enter(kind, { reduce: true, delay: 0.3 }), {}, `${kind}: motion off → no initial, animate or transition`);
    const on = enter(kind, { reduce: false });
    assert.ok(on.initial && on.animate && on.transition, `${kind}: animates with motion on`);
    assert.ok(on.transition.duration >= 0.15 && on.transition.duration <= 0.3, `${kind}: 150–300 ms`);
    assert.equal(on.animate.opacity, 1);
  }
  assert.equal(enter("user", { reduce: false }).initial?.x, 12, "the customer's bubble comes from the right");
  assert.equal(enter("agent", { reduce: false }).initial?.x, -12, "the agent's from the left");
  assert.equal(enter("part", { reduce: false }).initial?.y, 8, "rises 8 px");
  assert.equal(enter("receipt", { reduce: false }).initial?.scale, 0.97);
  assert.equal(enter("seal", { reduce: false }).initial?.scale, 1.15, "the seal stamps in");
});

test("spec 07 AC-26: the parts of a reply enter 60 ms apart in the fixed order steps → text → cards → chips", () => {
  assert.deepEqual([...REPLY_PARTS], ["steps", "text", "cards", "chips"]);
  const all = [...REPLY_PARTS];
  assert.deepEqual(all.map((p) => partDelay(p, all)), [0, 0.06, 0.12, 0.18]);
  assert.equal(partDelay("cards", ["text", "cards"]), 0.06, "a missing part leaves no gap");
  assert.equal(partDelay("text", ["cards", "text"]), 0, "the order is fixed, not the order given");
  assert.deepEqual([0, 1, 2].map((i) => cardDelay(i, 0.12)), [0.12, 0.16, 0.2], "option cards rise 40 ms apart");
});

test("spec 07 AC-13, AC-23: the person chip is always present and the primary chip is another one", () => {
  const person = { label: "Hablar con una persona", text: "Hablar con una persona", action: { type: "request_call" } } satisfies Suggestion;
  const view = { label: "Ver mi caso", text: "Ver mi caso", href: "/case/K-1" } satisfies Suggestion;
  const info = { label: "Agregar información", text: "Agregar información" } satisfies Suggestion;
  for (const row of [[], [info], [view, info, { label: "Otra", text: "Otra" }], [person, info]] as Suggestion[][]) {
    const chips = chipsFor(row, "es");
    assert.ok(chips.some((c) => isPersonChip(c, "es")), "talk to a person is always there");
    assert.ok(chips.length <= 3);
    const p = primaryChipIndex(chips, "es");
    if (p >= 0) assert.ok(!isPersonChip(chips[p], "es"), "the person chip is never the filled one");
  }
  assert.equal(primaryChipIndex(chipsFor([person, view], "es"), "es"), 1);
  assert.equal(primaryChipIndex(chipsFor([person], "es"), "es"), -1);
});
