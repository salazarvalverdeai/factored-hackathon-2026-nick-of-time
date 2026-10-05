"use client";

// How pages read data (spec 16 AC-03). In mock mode the data lives in lib/mock/store.ts; a page never imports the
// store directly: it calls `useQuery` to read and `api` (lib/api.ts) to act. When the backend exists, only this file
// and lib/api.ts change; the pages do not.
import { useSyncExternalStore } from "react";
import { ApiError } from "@/lib/api";
import { type MockState, type MockStore, mockStore } from "@/lib/mock/store";

const noopSubscribe = () => () => {};

/** False during server render and hydration, true afterwards: saved browser state is only read once mounted. */
export function useMounted(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

/** Re-renders the component whenever the mock data changes. */
export function useMockState(): MockState {
  return useSyncExternalStore(mockStore.subscribe, mockStore.getState, mockStore.getServerState);
}

export type Query<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ok"; data: T };

/** Reads through the same rules the backend enforces: no session → UNAUTHORIZED, expired → SESSION_EXPIRED, … */
export function useQuery<T>(read: (store: MockStore) => T): Query<T> {
  const mounted = useMounted();
  useMockState(); // subscribe: the read runs again after every change
  if (!mounted) return { status: "loading" };
  try {
    return { status: "ok", data: read(mockStore) };
  } catch (e) {
    if (e instanceof ApiError) return { status: "error", error: e };
    throw e;
  }
}
