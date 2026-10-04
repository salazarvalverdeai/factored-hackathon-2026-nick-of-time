// The one door the pages use to talk to the backend (spec 16 AC-03).
//  - mock mode (default): answers from lib/mock/store.ts, so every page works without the backend.
//  - live mode (NEXT_PUBLIC_API_MODE=live): not wired yet, it answers LIVE_API_NOT_READY until spec 05 ships.
import { type AgentContext, runAgentTurn } from "./mock/agent.ts";
import { CUSTOMERS } from "./mock/fixtures.ts";
import { ApiError, type MockStore, mockStore } from "./mock/store.ts";
import type { AgentReply, AnalystSession, CaseRecord, Customer, CustomerSession, NotificationEntry } from "./types.ts";

export type ApiMode = "mock" | "live";
export { ApiError };

export const API_MODE: ApiMode = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";

export interface ApiOptions {
  mode?: ApiMode;
  /** Simulated latency so loading states are visible in the demo; 0 in tests. */
  delayMs?: number;
}

export function createApi(store: MockStore, options: ApiOptions = {}) {
  const mode = options.mode ?? API_MODE;
  const delayMs = options.delayMs ?? (typeof window === "undefined" ? 0 : 450);

  async function call<T>(fn: () => T): Promise<T> {
    if (mode === "live") throw new ApiError("LIVE_API_NOT_READY", 501, "the live API arrives with spec 05");
    if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
    return fn();
  }

  return {
    mode,
    store,
    // customer
    listCustomers: (): Promise<Customer[]> => call(() => CUSTOMERS),
    requestOtp: (customerId: string): Promise<string> => call(() => store.requestOtp(customerId)),
    verifyOtp: (otp: string): Promise<CustomerSession> => call(() => store.verifyOtp(otp)),
    logoutCustomer: (): Promise<void> => call(() => store.logoutCustomer()),
    expireCustomerSession: (): Promise<void> => call(() => store.expireCustomerSession()),
    chat: (text: string, ctx?: AgentContext): Promise<AgentReply> => call(() => runAgentTurn(store, text, ctx)),
    // cases
    getCase: (id: string): Promise<CaseRecord> => call(() => store.getCase(id)),
    listCases: (): Promise<CaseRecord[]> => call(() => store.listCases()),
    getNotifications: (caseId: string): Promise<NotificationEntry[]> => call(() => store.notificationsFor(caseId)),
    requestCall: (caseId: string): Promise<void> => call(() => store.requestCall(caseId)),
    addCustomerInfo: (caseId: string, text: string): Promise<void> => call(() => store.addCustomerInfo(caseId, text)),
    createTelegramLink: (caseId: string) => call(() => store.createTelegramLink(caseId)),
    /** Mock only: plays the role of Telegram calling the webhook after the customer taps the deep link. */
    simulateTelegramStart: (caseId: string, token: string, secretHeaderOk = true): Promise<void> =>
      call(() => store.telegramStart(caseId, token, secretHeaderOk)),
    confirmEmail: (caseId: string, address: string): Promise<void> => call(() => store.confirmEmail(caseId, address)),
    // analyst
    analystLogin: (username: string, password: string): Promise<AnalystSession> => call(() => store.analystLogin(username, password)),
    analystLogout: (): Promise<void> => call(() => store.analystLogout()),
    approveCredit: (caseId: string, opts?: { confirmed?: boolean; reason?: string }): Promise<CaseRecord> =>
      call(() => store.approveCredit(caseId, opts)),
    closeCase: (caseId: string): Promise<CaseRecord> => call(() => store.closeCase(caseId)),
    setSupervised: (on: boolean): Promise<void> => call(() => store.setSupervised(on)),
  };
}

export type Api = ReturnType<typeof createApi>;

/** The client the app uses. */
export const api = createApi(mockStore);
