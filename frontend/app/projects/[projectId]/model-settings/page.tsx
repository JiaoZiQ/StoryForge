import { ModelSettingsPage } from "@/features/governance/model-settings-page";
export default async function ProjectModelSettingsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ModelSettingsPage projectId={Number(projectId)} />;
}
