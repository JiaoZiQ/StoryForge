import { BudgetPage } from "@/features/governance/budget-page";
export default async function ProjectBudgetPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <BudgetPage projectId={Number(projectId)} />;
}
