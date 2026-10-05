import type { Metadata } from "next";

// Tab title of /case/[id]; the root layout's template adds " · Nick of Time". `params` is a Promise in this version
// of Next.js (see node_modules/next/dist/docs).
export async function generateMetadata(props: LayoutProps<"/case/[id]">): Promise<Metadata> {
  const { id } = await props.params;
  return { title: `Case ${decodeURIComponent(id)}` };
}

export default function Layout({ children }: LayoutProps<"/case/[id]">) {
  return children;
}
