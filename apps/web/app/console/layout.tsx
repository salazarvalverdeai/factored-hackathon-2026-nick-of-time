import type { Metadata } from "next";

// Tab title of /console; the root layout's template adds " · Nick of Time". The page is a client component.
export const metadata: Metadata = { title: "Console" };

export default function Layout({ children }: LayoutProps<"/console">) {
  return children;
}
