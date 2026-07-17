import { ConflictPage } from "@/features/conflicts/conflict-page";
export default async function ConflictsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ConflictPage projectId={Number(projectId)} />;
}
