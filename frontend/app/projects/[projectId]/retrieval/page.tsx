import { RetrievalPage } from "@/features/retrieval/retrieval-page";
export default async function ProjectRetrievalPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <RetrievalPage projectId={Number(projectId)} />;
}
