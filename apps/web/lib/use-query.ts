"use client";

// How pages read data (spec 16 AC-03). A page never imports the mock store or fetches by hand: it reads with `useQuery`
// (any `api` call that returns a promise) and `useSession`, and acts with `api` (lib/api.ts). The same page code runs in
// mock and live mode; only lib/api.ts picks the client.
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, api } from "@/lib/api";
import type { ApiClient } from "@/lib/client";
import type { SessionSnapshot } from "@/lib/types";

const noopSubscribe = () => () => {};

/** False during server render and hydration, true afterwards: saved browser state is only read once mounted. */
export function useMounted(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

/** Who is signed in, supervised mode and this console session's audit; re-renders on every change. */
export function useSession(): SessionSnapshot {
  return useSyncExternalStore(api.subscribe, api.session.getSnapshot, api.session.getServerSnapshot);
}

export type Query<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ok"; data: T };

function asApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError("UNAVAILABLE", 0, "Something went wrong. Try again.");
}

/**
 * Loads `load(api)` once the page is mounted and again whenever `deps` change or the api reports a change (an action, a
 * login). While it reloads, the last data stays on screen, so the page does not flash. Rules the backend enforces come
 * back as an `error` (no session → UNAUTHORIZED, expired → SESSION_EXPIRED, …).
 */
export function useQuery<T>(load: (client: ApiClient) => Promise<T>, deps: readonly unknown[] = []): Query<T> {
  const mounted = useMounted();
  const [state, setState] = useState<Query<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);
  const loader = useRef(load);
  // The latest `load` is read by the effect below; it is kept in a ref after render so a new closure does not refetch.
  useLayoutEffect(() => {
    loader.current = load;
  });

  useEffect(() => api.subscribe(() => setTick((t) => t + 1)), []);

  useEffect(() => {
    if (!mounted) return;
    let alive = true;
    loader.current(api).then(
      (data) => alive && setState({ status: "ok", data }),
      (e: unknown) => alive && setState({ status: "error", error: asApiError(e) }),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, tick, ...deps]);

  return mounted ? state : { status: "loading" };
}
