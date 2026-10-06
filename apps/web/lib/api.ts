// The one door the pages use to talk to the backend (spec 16 AC-03).
//  - mock mode (default): answers from lib/mock/store.ts, so every page works without the backend.
//  - live mode (NEXT_PUBLIC_API_MODE=live): lib/live.ts answers from the spec 05 api; it never invents data.
// Both implement `ApiClient` (lib/client.ts), so a page does not know which one it talks to.
import type { ApiClient, ApiMode, ChatContext } from "./client.ts";
import { createLiveApi } from "./live.ts";
import { runAgentTurn } from "./mock/agent.ts";
import { DEMO_CUSTOMERS } from "./mock/fixtures.ts";
import { ApiError, type MockStore, caseStatus, mockStore } from "./mock/store.ts";
import type {
  AgentReply,
  AnalystSession,
  CallRequestResult,
  CaseRecord,
  CaseStatus,
  CustomerCaseView,
  CustomerSession,
  DemoCustomer,
  NotificationEntry,
} from "./types.ts";

export type { ApiClient, ApiMode };
export { ApiError };

export const API_MODE: ApiMode = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";

export interface ApiOptions {
  /** The mock client only: live mode is `createLiveApi` (lib/live.ts). */
  mode?: "mock";
  /** Simulated latency so loading states are visible in the demo; 0 in tests. */
  delayMs?: number;
}

function noVoice(): never {
  throw new ApiError("UNAVAILABLE", 501, "Voice needs the live api.");
}

function noDemo(): never {
  throw new ApiError("UNAVAILABLE", 501, "Demo sessions by scenario need the live api.");
}

export function createApi(store: MockStore, options: ApiOptions = {}) {
  const delayMs = options.delayMs ?? (typeof window === "undefined" ? 0 : 450);

  async function call<T>(fn: () => T): Promise<T> {
    if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
    return fn();
  }

  return {
    mode: "mock" as const,
    store,
    subscribe: store.subscribe,
    session: { getSnapshot: store.getState, getServerSnapshot: store.getServerState },
    // customer
    /** GET /api/demo/customers (spec 01 §6.2): never carries the score. */
    listDemoCustomers: (): Promise<DemoCustomer[]> => call(() => DEMO_CUSTOMERS),
    // Demo sessions by scenario, test charges and personas are the live api's (spec 05 AC-14 to AC-20): the mock has none.
    startDemoSession: (): Promise<string> => noDemo(),
    listScenarios: (): Promise<never[]> => noDemo(),
    listRecentTransactions: (): Promise<never[]> => noDemo(),
    registerTestCharge: (): Promise<never> => noDemo(),
    transcribe: (): Promise<never> => noVoice(),
    suggestPersona: (): Promise<never> => noDemo(),
    requestOtp: (customerId: string): Promise<string> => call(() => store.requestOtp(customerId)),
    verifyOtp: (otp: string): Promise<CustomerSession> => call(() => store.verifyOtp(otp)),
    logoutCustomer: (): Promise<void> => call(() => store.logoutCustomer()),
    expireCustomerSession: (): Promise<void> => call(() => store.expireCustomerSession()),
    chat: (text: string, ctx?: ChatContext): Promise<AgentReply> => call(() => runAgentTurn(store, text, ctx)),
    // cases
    /** GET /api/cases/{id}: the customer's projection. */
    getCase: (id: string): Promise<CustomerCaseView> => call(() => store.getCustomerCase(id)),
    /** GET /api/console/cases/{id}: the analyst's case with the handoff card. */
    getConsoleCase: (id: string): Promise<CaseRecord & { status: CaseStatus }> =>
      call(() => {
        const c = store.getCase(id);
        return { ...c, status: caseStatus(c) };
      }),
    listCases: (): Promise<(CaseRecord & { status: CaseStatus })[]> =>
      call(() => store.listCases().map((c) => ({ ...c, status: caseStatus(c) }))),
    getNotifications: (caseId: string): Promise<NotificationEntry[]> => call(() => store.notificationsFor(caseId)),
    requestCall: (caseId: string): Promise<CallRequestResult> => call(() => store.requestCall(caseId)),
    addCustomerInfo: (caseId: string, text: string): Promise<void> => call(() => store.addCustomerInfo(caseId, text)),
    createTelegramLink: (caseId: string) => call(() => store.createTelegramLink(caseId)),
    /** Mock only: plays the role of Telegram calling the webhook after the customer taps the deep link. */
    simulateTelegramStart: (caseId: string, token: string, secretHeaderOk = true): Promise<void> =>
      call(() => store.telegramStart(caseId, token, secretHeaderOk)),
    confirmEmail: (caseId: string, address: string): Promise<void> => call(() => store.confirmEmail(caseId, address)),
    // analyst
    analystLogin: (username: string, password: string): Promise<AnalystSession> => call(() => store.analystLogin(username, password)),
    analystLogout: (): Promise<void> => call(() => store.analystLogout()),
    /** `approve_credit` and `close_case` are the two moves of the mock queue (see consoleActions). */
    analystAction: (caseId: string, action: string, opts?: { confirmed?: boolean; reason?: string }): Promise<CaseRecord> =>
      call(() => {
        if (action === "approve_credit") return store.approveCredit(caseId, opts);
        if (action === "close_case") return store.closeCase(caseId);
        throw new ApiError("INVALID_TRANSITION", 409, `${action} is not part of the mock queue`);
      }),
    approveCredit: (caseId: string, opts?: { confirmed?: boolean; reason?: string }): Promise<CaseRecord> =>
      call(() => store.approveCredit(caseId, opts)),
    closeCase: (caseId: string): Promise<CaseRecord> => call(() => store.closeCase(caseId)),
    setSupervised: (on: boolean): Promise<void> => call(() => store.setSupervised(on)),
  };
}

export type MockApi = ReturnType<typeof createApi>;

/** The client the app uses: chosen once, at build time, by NEXT_PUBLIC_API_MODE. */
export const api: ApiClient = API_MODE === "live" ? createLiveApi() : createApi(mockStore);
