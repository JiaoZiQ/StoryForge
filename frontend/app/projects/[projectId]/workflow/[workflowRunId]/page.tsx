import { WorkflowDetail } from "@/features/workflows/workflow-detail";
export default async function WorkflowRunPage({
  params,
}: {
  params: Promise<{ projectId: string; workflowRunId: string }>;
}) {
  const { projectId, workflowRunId } = await params;
  return (
    <WorkflowDetail
      projectId={Number(projectId)}
      workflowRunId={Number(workflowRunId)}
    />
  );
}
