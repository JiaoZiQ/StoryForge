"use client";

import Link from "next/link";
import { useState } from "react";
import { useProjects } from "@/hooks/use-storyforge";
import { PageHeader } from "@/components/ui/page";
import {
  EmptyState,
  ErrorState,
  PageLoading,
  Pagination,
  StatusBadge,
} from "@/components/ui/states";
import { formatDate } from "@/lib/formatting";

export function ProjectList() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [genre, setGenre] = useState("");
  const query = useProjects({
    page,
    pageSize: 20,
    search: search || undefined,
    status: status || undefined,
    genre: genre || undefined,
  });
  return (
    <>
      <PageHeader
        eyebrow="Library"
        title="Projects"
        description="Search and filter project metadata. Chapter content is never fetched by this list."
        actions={
          <Link className="button-primary" href="/projects/new">
            New project
          </Link>
        }
      />
      <form
        className="surface mb-5 grid gap-3 rounded-xl p-4 sm:grid-cols-3"
        onSubmit={(event) => event.preventDefault()}
        aria-label="Project filters"
      >
        <label className="label">
          Search
          <input
            className="field"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            placeholder="Title or premise"
          />
        </label>
        <label className="label">
          Status
          <select
            className="field"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {[
              "created",
              "planned",
              "generating",
              "accepted",
              "needs_review",
              "failed",
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="label">
          Genre
          <input
            className="field"
            value={genre}
            onChange={(event) => {
              setGenre(event.target.value);
              setPage(1);
            }}
            placeholder="e.g. mystery"
          />
        </label>
      </form>
      {query.isLoading ? (
        <PageLoading />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data!.items.length === 0 ? (
        <EmptyState
          title="No matching projects"
          message="Adjust the filters or create a new story project."
        />
      ) : (
        <section className="surface rounded-xl p-4">
          <div className="table-wrap">
            <table>
              <caption>Story projects</caption>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Genre</th>
                  <th>Status</th>
                  <th>Language</th>
                  <th>Target</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {query.data!.items.map((project) => (
                  <tr key={project.id}>
                    <td>
                      <Link
                        className="font-bold text-copper-dark underline-offset-4 hover:underline"
                        href={`/projects/${project.id}`}
                      >
                        {project.title}
                      </Link>
                    </td>
                    <td>{project.genre}</td>
                    <td>
                      <StatusBadge value={project.status} />
                    </td>
                    <td>{project.language}</td>
                    <td>{project.target_chapters} chapters</td>
                    <td>{formatDate(project.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={query.data!.meta.page}
            totalPages={query.data!.meta.total_pages}
            onPage={setPage}
          />
        </section>
      )}
    </>
  );
}
