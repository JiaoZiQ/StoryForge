import { ChapterList } from "@/features/chapters/chapter-list";
export default async function ChaptersPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ChapterList projectId={Number(projectId)} />;
}
