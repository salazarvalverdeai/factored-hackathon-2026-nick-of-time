import type { Metadata } from "next";

// Tab title of /analytics; the root layout's template adds " · Nick of Time". A layout keeps the page file untouched.
export const metadata: Metadata = { title: "Analytics" };

export default function Layout({ children }: LayoutProps<"/analytics">) {
  return children;
}
