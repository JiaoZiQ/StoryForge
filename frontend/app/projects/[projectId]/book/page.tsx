import { BookRunsPage } from "@/features/books/book-runs-page";

export default async function BookPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <BookRunsPage projectId={Number(projectId)} />;
}
