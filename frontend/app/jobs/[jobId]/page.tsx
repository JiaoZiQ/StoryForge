import { JobDetail } from "@/features/jobs/job-detail";

export default async function JobPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <JobDetail jobId={Number(jobId)} />;
}
