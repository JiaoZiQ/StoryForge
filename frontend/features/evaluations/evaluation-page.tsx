"use client";

import { useState } from "react";
import { useChapters } from "@/hooks/use-storyforge";
import { PageHeader, Section } from "@/components/ui/page";
import { ErrorState, PageLoading } from "@/components/ui/states";
import { EvaluationPanel } from "./evaluation-panel";

export function EvaluationPage({ projectId }: { projectId: number }) {
  const chapters = useChapters(projectId);
  const [selectedChapter, setSelectedChapter] = useState(0);
  const chapter =
    selectedChapter || chapters.data?.items[0]?.chapter_number || 0;
  if (chapters.isLoading) return <PageLoading />;
  if (chapters.error) return <ErrorState error={chapters.error} />;
  return (
    <>
      <PageHeader
        eyebrow="Quality"
        title="Evaluations"
        description="Mechanical, critic, and consistency scores remain tied to immutable chapter versions."
      />
      <Section title="Evaluation history">
        <label className="label mb-5 max-w-sm">
          Chapter
          <select
            className="field"
            value={chapter}
            onChange={(event) => setSelectedChapter(Number(event.target.value))}
          >
            {chapters.data!.items.map((item) => (
              <option key={item.id} value={item.chapter_number}>
                {item.chapter_number}. {item.title}
              </option>
            ))}
          </select>
        </label>
        {chapter ? (
          <EvaluationPanel projectId={projectId} chapterNumber={chapter} />
        ) : (
          <p className="text-ink-600">No planned chapters.</p>
        )}
      </Section>
    </>
  );
}
