// The en dictionary: every namespace in en (spec 16 AC-06). Edit the namespace files, not this one.
import { shell } from "./shell.ts";
import { landing } from "./landing.ts";
import { chat } from "./chat.ts";
import { trace } from "./trace.ts";
import { consoleUi } from "./console.ts";
import { login } from "./login.ts";
import { caseView } from "./caseView.ts";
import { agent } from "./agent.ts";
import { analytics } from "./analytics.ts";
import { evaluation } from "./evaluation.ts";
import { data } from "./data.ts";
import { ui } from "./ui.ts";

export const en = {
  shell: shell.en,
  landing: landing.en,
  chat: chat.en,
  trace: trace.en,
  console: consoleUi.en,
  login: login.en,
  caseView: caseView.en,
  agent: agent.en,
  analytics: analytics.en,
  evaluation: evaluation.en,
  data: data.en,
  ui: ui.en,
};
