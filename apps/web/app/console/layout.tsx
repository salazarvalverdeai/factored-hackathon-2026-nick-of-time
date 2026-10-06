import type { Metadata } from "next";
import { getT } from "@/lib/i18n-server";

// Tab title of /console in the UI language; the root layout's template adds " · Nick of Time". The page is a client
// component.
export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: t("console.meta.title") };
}

export default function Layout({ children }: LayoutProps<"/console">) {
  return children;
}
