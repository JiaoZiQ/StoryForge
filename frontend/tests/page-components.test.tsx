import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader, Section, StatCard } from "@/components/ui/page";

describe("page primitives", () => {
  it("renders semantic headings, descriptions and actions", () => {
    render(
      <>
        <PageHeader
          eyebrow="Library"
          title="Projects"
          description="Manage story projects"
          actions={<button type="button">Create</button>}
        />
        <StatCard label="Ready" value={3} detail="projects" />
        <Section title="Recent" description="Latest activity">
          One project
        </Section>
      </>,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Projects",
    );
    expect(screen.getByRole("button", { name: "Create" })).toBeVisible();
    expect(screen.getByText("Latest activity")).toBeVisible();
    expect(screen.getByText("projects")).toBeVisible();
  });
});
