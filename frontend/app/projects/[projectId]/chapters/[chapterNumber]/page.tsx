import { ChapterDetailView } from "@/features/chapters/chapter-detail";
export default async function ChapterPage({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string; chapterNumber: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const [{ projectId, chapterNumber }, query] = await Promise.all([
    params,
    searchParams,
  ]);
  return (
    <ChapterDetailView
      projectId={Number(projectId)}
      chapterNumber={Number(chapterNumber)}
      initialTab={query.tab}
    />
  );
}
