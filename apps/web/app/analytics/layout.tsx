import type { Metadata } from "next";
import { getT } from "@/lib/i18n-server";

// Tab title of /analytics in the UI language; the root layout's template adds " · Nick of Time". A layout keeps the
// page file untouched.
export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: t("analytics.meta.title") };
}

export default function Layout({ children }: LayoutProps<"/analytics">) {
  return children;
}
