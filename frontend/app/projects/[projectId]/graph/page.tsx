import { GraphPage } from "@/features/graph/graph-page";
export default async function ProjectGraphPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <GraphPage projectId={Number(projectId)} />;
}
