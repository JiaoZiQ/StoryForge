import { MemoryPage } from "@/features/memory/memory-page";
export default async function ProjectMemoryPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <MemoryPage projectId={Number(projectId)} />;
}
