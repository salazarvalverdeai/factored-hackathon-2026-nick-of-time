// The es dictionary: every namespace in es (spec 16 AC-06). Edit the namespace files, not this one.
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

export const es = {
  shell: shell.es,
  landing: landing.es,
  chat: chat.es,
  trace: trace.es,
  console: consoleUi.es,
  login: login.es,
  caseView: caseView.es,
  agent: agent.es,
  analytics: analytics.es,
  evaluation: evaluation.es,
  data: data.es,
  ui: ui.es,
};
