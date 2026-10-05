import type { Metadata } from "next";

// Tab title of /login; the root layout's template adds " · Nick of Time". The page is a client component.
export const metadata: Metadata = { title: "Analyst login" };

export default function Layout({ children }: LayoutProps<"/login">) {
  return children;
}
