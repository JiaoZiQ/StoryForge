import { PlanView } from "@/features/plan/plan-view";
export default async function PlanPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <PlanView projectId={Number(projectId)} />;
}
