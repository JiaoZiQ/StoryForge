import { FactPage } from "@/features/facts/fact-page";
export default async function FactsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <FactPage projectId={Number(projectId)} />;
}
