// Offline checks for the /chat page helpers (spec 07 AC-07, AC-09). Each test cites the criterion it covers.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { agentGreeted, greetingName, helloLine, showWebGreeting } from "./chat-view.ts";
import { MESSAGES, fill } from "./mock/messages.ts";

const DEMO = JSON.parse(readFileSync(new URL("../../../eval/demo/customers.json", import.meta.url), "utf8")) as { display_name: string }[];

test("spec 07 AC-07: the web greets with the whole first name of the picker label, compound names included", () => {
  assert.equal(greetingName("Gerardo Lucas (MX · debit)"), "Gerardo Lucas");
  assert.equal(greetingName("Ana (MX debit)"), "Ana");
  assert.equal(greetingName("Verónica"), "Verónica");
  assert.equal(greetingName(undefined), "");
  for (const c of DEMO) assert.ok(!greetingName(c.display_name).includes("("), c.display_name);
});

test("spec 07 AC-07: the web greets with the name it has, and with no name drops it (never 'Hola, you')", () => {
  assert.equal(helloLine("es", "Ana"), fill(MESSAGES.greet.hello, "es", { first_name: "Ana" }));
  assert.equal(helloLine("pt", " Bruno "), fill(MESSAGES.greet.hello, "pt", { first_name: "Bruno" }));
  assert.match(helloLine("es", ""), /^Hola\. Soy /);
  assert.match(helloLine("pt", "  "), /^Olá\. Sou /);
  for (const lang of ["es", "pt"] as const) assert.ok(!/\{first_name\}|,\s*\.|\byou\b/.test(helloLine(lang, "")));
});

test("spec 07 AC-07: the agent's greeting of contracts/messages.yaml is recognized in ES and PT", () => {
  const es = [fill(MESSAGES.greet.hello, "es", { first_name: "Gerardo Lucas" }), MESSAGES.greet.capability_1.es].join("\n");
  const pt = fill(MESSAGES.greet.hello, "pt", { first_name: "Verónica" });
  assert.ok(agentGreeted(es));
  assert.ok(agentGreeted(pt));
  assert.ok(!agentGreeted("Esto es lo que voy a hacer:\n1. Abrir un caso."));
  assert.ok(!agentGreeted("Hola"));
});

test("spec 07 AC-07: exactly one greeting: the web's goes once the agent greets, and stays when it does not", () => {
  const hello = fill(MESSAGES.greet.hello, "es", { first_name: "Gerardo Lucas" });
  assert.equal(showWebGreeting([]), true);
  assert.equal(showWebGreeting([{ role: "customer", text: "No reconozco un cargo" }]), true, "until the agent answers");
  assert.equal(showWebGreeting([{ role: "customer", text: "hola" }, { role: "agent", text: `${hello}\n- Ayudarte` }]), false);
  assert.equal(
    showWebGreeting([{ role: "customer", text: "hola" }, { role: "agent", text: "Esto es lo que voy a hacer:" }]),
    true,
    "the mock agent never greets: the web's greeting is the only one",
  );
});

test("spec 07 AC-09: chat bubbles keep line breaks as text, never as HTML", () => {
  const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
  const thread = read("../components/chat/thread.tsx");
  const markdown = read("../components/chat/markdown.tsx");
  const panel = read("../components/chat/trace-panel.tsx");
  const page = read("../app/chat/page.tsx");
  assert.match(thread, /whitespace-pre-line[^"`]*rounded-2xl/, "the customer bubble keeps \\n as a line break");
  assert.match(markdown, /<p className="whitespace-pre-line/, "an agent paragraph keeps \\n as a line break");
  assert.match(markdown, /skipHtml/, "raw HTML in a reply is skipped, never rendered");
  assert.match(panel, /whitespace-pre-line/, "the plan step keeps its numbered lines");
  for (const src of [page, thread, markdown, panel]) assert.ok(!src.includes("dangerouslySetInnerHTML"), "a reply is never parsed as HTML");
});
