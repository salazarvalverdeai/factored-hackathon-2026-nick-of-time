import type { Metadata } from "next";

// Tab title of /data; the root layout's template adds " · Nick of Time". A layout keeps the page file untouched.
export const metadata: Metadata = { title: "Data" };

export default function Layout({ children }: LayoutProps<"/data">) {
  return children;
}
