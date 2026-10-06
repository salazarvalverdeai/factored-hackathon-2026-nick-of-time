// The pt dictionary: every namespace in pt (spec 16 AC-06). Edit the namespace files, not this one.
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

export const pt = {
  shell: shell.pt,
  landing: landing.pt,
  chat: chat.pt,
  trace: trace.pt,
  console: consoleUi.pt,
  login: login.pt,
  caseView: caseView.pt,
  agent: agent.pt,
  analytics: analytics.pt,
  evaluation: evaluation.pt,
  data: data.pt,
  ui: ui.pt,
};
