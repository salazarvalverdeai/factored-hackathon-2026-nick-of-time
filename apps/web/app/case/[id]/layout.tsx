import type { Metadata } from "next";
import { getT } from "@/lib/i18n-server";

// Tab title of /case/[id] in the UI language; the root layout's template adds " · Nick of Time". `params` is a Promise
// in this version of Next.js (see node_modules/next/dist/docs).
export async function generateMetadata(props: LayoutProps<"/case/[id]">): Promise<Metadata> {
  const { id } = await props.params;
  const { t } = await getT();
  return { title: t("caseView.meta.title", { id: decodeURIComponent(id) }) };
}

export default function Layout({ children }: LayoutProps<"/case/[id]">) {
  return children;
}
