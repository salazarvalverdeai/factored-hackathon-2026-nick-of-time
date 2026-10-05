// Pure helpers of the /chat page (spec 07 AC-07): one greeting, with the same name the picker and the agent use.
import { MESSAGES } from "./mock/messages.ts";

/**
 * The name the web greets with: the picker label without its "(country · product)" tag. The api builds that label
 * from gold's first name, the one `get_customer_profile` returns, so a compound name ("Gerardo Lucas") is kept whole.
 */
export function greetingName(displayName: string | undefined): string {
  return (displayName ?? "").replace(/\s*\([^)]*\)\s*$/, "").trim();
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** greet.hello of contracts/messages.yaml in ES and PT, with {first_name} matching any name. */
const HELLO = Object.values(MESSAGES.greet.hello).map(
  (template) => new RegExp(`^${template.split("{first_name}").map(escape).join(".+?")}`),
);

/** True when an agent reply opens with the greeting of spec 04 AC-15 (the first reply of a live session). */
export function agentGreeted(text: string): boolean {
  const first = text.trimStart().split("\n", 1)[0];
  return HELLO.some((re) => re.test(first));
}

/**
 * The web shows its own greeting until the agent greets: then the agent's greeting is the only one. The mock agent
 * never greets, so in mock mode the web's greeting stays at the top of the conversation.
 */
export function showWebGreeting(messages: readonly { role: "customer" | "agent"; text: string }[]): boolean {
  return !messages.some((m) => m.role === "agent" && agentGreeted(m.text));
}
