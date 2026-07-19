import { BookRunWorkspace } from "@/features/books/book-run-workspace";

export default async function BookRunPage({
  params,
}: {
  params: Promise<{ projectId: string; bookRunId: string }>;
}) {
  const { projectId, bookRunId } = await params;
  return (
    <BookRunWorkspace projectId={Number(projectId)} runId={Number(bookRunId)} />
  );
}
