import { WorkflowList } from "@/features/workflows/workflow-list";
export default async function WorkflowPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <WorkflowList projectId={Number(projectId)} />;
}
