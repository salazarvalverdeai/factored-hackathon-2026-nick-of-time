import type { Metadata } from "next";

// Tab title of /chat; the root layout's template adds " · Nick of Time". The page is a client component.
export const metadata: Metadata = { title: "Chat" };

export default function Layout({ children }: LayoutProps<"/chat">) {
  return children;
}
