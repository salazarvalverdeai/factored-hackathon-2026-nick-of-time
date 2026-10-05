import type { Metadata } from "next";

// Tab title of /evaluation; the root layout's template adds " · Nick of Time". A layout keeps the page file untouched.
export const metadata: Metadata = { title: "Evaluation" };

export default function Layout({ children }: LayoutProps<"/evaluation">) {
  return children;
}
