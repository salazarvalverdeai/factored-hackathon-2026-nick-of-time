import type { Metadata } from "next";
import { getT } from "@/lib/i18n-server";

// Tab title of /chat in the UI locale; the root layout's template adds " · Nick of Time". The page is a client component.
export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: t("chat.meta.title") };
}

export default function Layout({ children }: LayoutProps<"/chat">) {
  return children;
}
