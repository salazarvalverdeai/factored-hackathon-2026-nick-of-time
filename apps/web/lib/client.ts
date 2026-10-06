// The surface the pages use (spec 16 AC-03). Two implementations answer it: the mock (lib/api.ts, over lib/mock/store.ts)
// and the live one (lib/live.ts, over the spec 05 api). A page never knows which one it is talking to.
import type { TextChunk, ToolEvent } from "./chat-stream.ts";
import type {
  AgentReply,
  AnalystSession,
  CallRequestResult,
  CaseListItem,
  ConsoleCase,
  CustomerCaseView,
  CustomerSession,
  DemoCustomer,
  NotificationEntry,
  ProgressLabel,
  SessionSnapshot,
  TurnAction,
} from "./types.ts";

export type ApiMode = "mock" | "live";

export interface ChatContext {
  /** Mock only: the request waiting for the customer's confirmation. */
  pendingRequest?: string;
  /** A chip press: it is sent instead of text and skips the classifier (spec 01 §6.4). */
  action?: TurnAction;
  /** Live: one label per step of the run, as the agent works (spec 04 AC-17). */
  onProgress?: (item: ProgressLabel) => void;
  /** Each tool call as it starts and ends, with its cards (spec 01 §6.4.1). The mock plays the same events. */
  onTool?: (event: ToolEvent) => void;
  /** Each chunk of the reply being written (writer `llm` only; spec 01 AC-10). */
  onText?: (chunk: TextChunk) => void;
}

export interface ApiClient {
  mode: ApiMode;
  /** Called after every change a page may need to read again (an action, a login, a logout). */
  subscribe: (listener: () => void) => () => void;
  session: { getSnapshot: () => SessionSnapshot; getServerSnapshot: () => SessionSnapshot };

  // customer
  listDemoCustomers: () => Promise<DemoCustomer[]>;
  /** Opens a session for the picked demo customer and returns the one-time code to show on screen [simulated]. */
  requestOtp: (customerId: string) => Promise<string>;
  verifyOtp: (otp: string) => Promise<CustomerSession>;
  logoutCustomer: () => Promise<void>;
  /** Demo button: ends the session now. Live mode has no such route, so the page does not offer it. */
  expireCustomerSession: () => Promise<void>;
  chat: (text: string, ctx?: ChatContext) => Promise<AgentReply>;

  // cases
  getCase: (id: string) => Promise<CustomerCaseView>;
  getConsoleCase: (id: string) => Promise<ConsoleCase>;
  listCases: () => Promise<CaseListItem[]>;
  getNotifications: (caseId: string) => Promise<NotificationEntry[]>;
  requestCall: (caseId: string) => Promise<CallRequestResult>;
  addCustomerInfo: (caseId: string, text: string) => Promise<void>;
  /** `token` is empty in live mode: the deep link carries it and Telegram calls the webhook itself. */
  createTelegramLink: (caseId: string) => Promise<{ token: string; deepLink: string }>;
  /** Mock only: plays the role of Telegram calling the webhook after the customer taps the deep link. */
  simulateTelegramStart: (caseId: string, token: string, secretHeaderOk?: boolean) => Promise<void>;
  /** Mock: confirmed at once. Live: a link is e-mailed and the address counts once the customer opens it. */
  confirmEmail: (caseId: string, address: string) => Promise<void>;

  // analyst
  analystLogin: (username: string, password: string) => Promise<AnalystSession>;
  analystLogout: () => Promise<void>;
  /** One analyst action (`consoleActions` says which ones a status offers). The api records who did it (spec 05 AC-07). */
  analystAction: (caseId: string, action: string, opts?: { reason?: string; confirmed?: boolean }) => Promise<unknown>;
  setSupervised: (on: boolean) => Promise<void>;
}
