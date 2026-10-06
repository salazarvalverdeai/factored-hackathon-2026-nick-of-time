// The assisted console's own api calls (spec 08 assisted case view, spec 18 T5/T5b). Analyst-only routes:
//   GET  /api/console/cases/{id}/context         customer history around the case
//   GET  /api/console/cases/{id}/conversation    the customer–agent transcript, read-only
//   GET  /api/console/cases/{id}/summary         the agent's summary and the nearest legal deadline
//   GET  /api/console/cases/{id}/second-opinion  the judge's advisory opinion (404 = none yet)
//   POST /api/console/cases/{id}/second-opinion  ask the judge; null or 204 = "No second opinion" (spec 18 AC-11)
//   GET  /api/console/cases/{id}/audit           the deterministic auditor A1–A7 (spec 18 §4.1)
// Mock mode answers from lib/mock/console.ts (simulated, built from the mock case); live mode calls the api with the
// analyst's id token and never invents data. Kept apart from lib/live.ts and lib/types.ts, which the /chat lane owns.
import { api } from "./api.ts";
import { ApiError } from "./mock/store.ts";
import { mockAudit, mockContext, mockConversation, mockSecondOpinion, mockSummary } from "./mock/console.ts";
import type { ConsoleCase, NotificationEntry } from "./types.ts";

// --- shapes (the api lane's contract for these routes) ----------------------------------------------------------------

export type CaseOutcome = string;

export interface PreviousCase {
  case_id: string;
  opened_at: string;
  status: string;
  outcome: CaseOutcome | null;
}

export interface ContextTransaction {
  transaction_id: string;
  /** YYYY-MM-DD or an ISO timestamp. */
  date: string;
  amount: number;
  currency: string;
  merchant: string;
  last4: string;
  /** The charge this case disputes. */
  disputed: boolean;
}

export interface ContextCard {
  last4: string;
  product: string;
  status: string;
}

export interface ContextCall {
  requested_at: string;
  status: string;
}

export interface ContextNotification {
  at: string;
  channel: string;
  event: string;
  status: string;
}

export interface CaseContext {
  previous_cases: PreviousCase[];
  /** The customer's transactions within ±30 days of the disputed one. */
  transactions: ContextTransaction[];
  cards: ContextCard[];
  calls: ContextCall[];
  notifications: ContextNotification[];
}

export interface SummaryDeadline {
  kind: string;
  /** YYYY-MM-DD. */
  date: string;
  days_left: number | null;
  source_label: string;
  source_url: string | null;
}

export interface CaseSummary {
  lines: string[];
  writer: "llm" | "template";
  /** Null when the country has no verified clock entry (POL-CLOCK-UNKNOWN): a person decides, no date is invented. */
  deadline: SummaryDeadline | null;
}

export type Verdict = "agree" | "disagree" | "uncertain";

export interface SecondOpinion {
  verdict: Verdict;
  reasons: { text: string; evidence_ids: string[] }[];
  questions?: { text: string; evidence_ids: string[] }[];
  model: string;
  label: string;
  created_at: string;
}

export interface AuditCheck {
  id: string;
  name: string;
  /** null = not applicable to this case (spec 18 AC-06). */
  passed: boolean | null;
  detail: string;
}

export interface AuditResult {
  checks: AuditCheck[];
  rederived_outcome: string;
  matches: boolean;
}

/** The copilot proposal of the handoff card with the api's plain-words `explanation` (optional until the api sends it). */
export interface CopilotProposal {
  action: string;
  rationale: string;
  requires_human: boolean;
  explanation?: string;
}

export interface TranscriptMessage {
  role: "customer" | "agent";
  text: string;
  at: string;
}

/** The customer–agent transcript of a case, one thread per chat session (analyst only, read-only). */
export interface CaseConversation {
  threads: { thread_id: string; session_started_at: string; messages: TranscriptMessage[] }[];
}

export interface ConsoleApi {
  getContext: (caseId: string) => Promise<CaseContext>;
  getConversation: (caseId: string) => Promise<CaseConversation>;
  getSummary: (caseId: string) => Promise<CaseSummary>;
  /** The opinion already issued for this case, or null. */
  getSecondOpinion: (caseId: string) => Promise<SecondOpinion | null>;
  /** Asks the judge; null means "No second opinion" (it failed, timed out or was over budget). */
  requestSecondOpinion: (caseId: string) => Promise<SecondOpinion | null>;
  getAudit: (caseId: string) => Promise<AuditResult>;
}

// --- clients ------------------------------------------------------------------------------------------------------

export interface MockDeps {
  getCase: (id: string) => Promise<ConsoleCase>;
  getNotifications?: (caseId: string) => Promise<NotificationEntry[]>;
  /** Simulated latency so the loading states are visible; 0 in tests. */
  delayMs?: number;
}

export function createMockConsoleApi(deps: MockDeps): ConsoleApi {
  const opinions = new Map<string, SecondOpinion | null>();
  const wait = () => new Promise((r) => setTimeout(r, deps.delayMs ?? 0));
  return {
    async getContext(id) {
      const c = await deps.getCase(id);
      const notes = deps.getNotifications ? await deps.getNotifications(id).catch(() => []) : [];
      return mockContext(c, notes);
    },
    async getConversation(id) {
      return mockConversation(await deps.getCase(id));
    },
    async getSummary(id) {
      return mockSummary(await deps.getCase(id));
    },
    async getSecondOpinion(id) {
      return opinions.get(id) ?? null;
    },
    async requestSecondOpinion(id) {
      const c = await deps.getCase(id);
      await wait();
      const out = mockSecondOpinion(c);
      opinions.set(id, out);
      return out;
    },
    async getAudit(id) {
      return mockAudit(await deps.getCase(id));
    },
  };
}

export interface LiveDeps {
  fetch?: typeof fetch;
  baseUrl?: string;
  /** The analyst's id token; by default the one lib/live.ts keeps in this tab's sessionStorage. */
  token?: () => string | null;
}

const LIVE_STORAGE_KEY = "nickoftime.live.v1";

/** The analyst token lib/live.ts stores after the Cognito sign-in (read only; that file owns it). */
export function storedAnalystToken(storage: Pick<Storage, "getItem"> | null = browserSession()): string | null {
  try {
    const raw = storage?.getItem(LIVE_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as { analyst?: { token?: string; expiresAt?: number } | null }) : null;
    const a = parsed?.analyst;
    if (!a?.token || (a.expiresAt !== undefined && a.expiresAt <= Date.now())) return null;
    return a.token;
  } catch {
    return null;
  }
}

function browserSession(): Pick<Storage, "getItem"> | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function createLiveConsoleApi(deps: LiveDeps = {}): ConsoleApi {
  const base = deps.baseUrl ?? "";
  const doFetch: typeof fetch = deps.fetch ?? ((...args) => fetch(...args));
  const token = deps.token ?? (() => storedAnalystToken());

  async function send(path: string, method = "GET", allow404 = false): Promise<unknown> {
    const t = token();
    if (!t) throw new ApiError("UNAUTHORIZED", 401, "Sign in first.");
    let res: Response;
    try {
      res = await doFetch(`${base}${path}`, {
        method,
        headers: { Accept: "application/json", Authorization: `Bearer ${t}` },
        credentials: "same-origin",
      });
    } catch {
      throw new ApiError("UNAVAILABLE", 0, "Cannot reach the server. Check your connection and try again.");
    }
    if (allow404 && res.status === 404) return null;
    if (res.status === 204) return null;
    if (!res.ok) {
      const b = (await res.json().catch(() => ({}))) as { code?: string; message?: string };
      if (res.status === 401) throw new ApiError("UNAUTHORIZED", 401, "Your sign-in expired or was not accepted: sign in again.");
      throw new ApiError(b.code ?? "UNAVAILABLE", res.status, b.message ?? `The api answered ${res.status}`);
    }
    return res.json().catch(() => null);
  }

  const path = (id: string, leaf: string) => `/api/console/cases/${encodeURIComponent(id)}/${leaf}`;
  const opinion = (v: unknown): SecondOpinion | null =>
    v && typeof v === "object" && "verdict" in v ? (v as SecondOpinion) : null;

  return {
    getContext: async (id) => (await send(path(id, "context"))) as CaseContext,
    getConversation: async (id) => ((await send(path(id, "conversation"))) as CaseConversation | null) ?? { threads: [] },
    getSummary: async (id) => (await send(path(id, "summary"))) as CaseSummary,
    getSecondOpinion: async (id) => opinion(await send(path(id, "second-opinion"), "GET", true)),
    requestSecondOpinion: async (id) => opinion(await send(path(id, "second-opinion"), "POST")),
    getAudit: async (id) => (await send(path(id, "audit"))) as AuditResult,
  };
}

/** The client the console uses, in the same mode as `api` (lib/api.ts). */
export const consoleApi: ConsoleApi =
  api.mode === "live"
    ? createLiveConsoleApi()
    : createMockConsoleApi({
        getCase: (id) => api.getConsoleCase(id),
        delayMs: typeof window === "undefined" ? 0 : 600,
      });
