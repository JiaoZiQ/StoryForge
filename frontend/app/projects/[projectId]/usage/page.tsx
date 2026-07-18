import { UsagePage } from "@/features/governance/usage-page";
export default async function ProjectUsagePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <UsagePage projectId={Number(projectId)} />;
}
