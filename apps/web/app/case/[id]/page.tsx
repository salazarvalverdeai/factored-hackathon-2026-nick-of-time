import { CaseView } from "./case-view";

// `params` is a Promise in this version of Next.js (see node_modules/next/dist/docs).
export default async function CasePage(props: PageProps<"/case/[id]">) {
  const { id } = await props.params;
  return <CaseView id={decodeURIComponent(id)} />;
}
