import { EvaluationPage } from "@/features/evaluations/evaluation-page";
export default async function EvaluationsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <EvaluationPage projectId={Number(projectId)} />;
}
