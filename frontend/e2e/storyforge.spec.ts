import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  apiJson,
  createAcceptedProject,
  createPlannedProject,
} from "./helpers";

test("creates a project and generates its plan from the UI", async ({
  page,
}) => {
  const title = `M9 browser create ${Date.now()}`;
  await page.goto("/projects/new");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Genre").fill("mystery");
  await page
    .getByLabel("Premise")
    .fill("A cartographer discovers a door erased from every city plan.");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);

  await page.getByRole("link", { name: "View plan" }).click();
  await page.getByRole("button", { name: "Generate plan" }).click();
  await expect(page.getByRole("heading", { name: "Story plan" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Chapter outline" }),
  ).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(
    accessibility.violations.filter((item) =>
      ["critical", "serious"].includes(item.impact ?? ""),
    ),
  ).toEqual([]);
});

test("runs a revision workflow and exposes immutable evaluation history", async ({
  page,
  request,
}) => {
  const project = await createPlannedProject(request, "workflow");
  await page.goto(`/projects/${project.id}/chapters/1`);
  await page.getByRole("button", { name: "Run full workflow" }).click();
  await expect(page).toHaveURL(/\/workflow\/\d+$/);
  await expect(
    page.getByText("Status: Completed", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/1\/3|2\/3|3\/3/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0);

  await page.goto(`/projects/${project.id}/chapters/1?tab=versions`);
  await expect(page.getByText("Immutable chapter versions")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Compare versions" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Evaluations" }).click();
  await expect(page.getByText("Dimension scores")).toBeVisible();
});

test("retrieval and graph pages explain accepted past-only memory", async ({
  page,
  request,
}) => {
  const { project } = await createAcceptedProject(request, "memory");
  await page.goto(`/projects/${project.id}/retrieval`);
  await page.getByRole("button", { name: "Run retrieval" }).click();
  await expect(page.getByRole("heading", { name: "Final hits" })).toBeVisible();
  const main = page.getByRole("main");
  await expect(main.getByText("Keyword", { exact: true })).toBeVisible();
  await expect(main.getByText("Vector", { exact: true })).toBeVisible();
  await expect(main.getByText("Fact", { exact: true })).toBeVisible();
  await expect(main.getByText("Graph", { exact: true })).toBeVisible();

  await page.goto(`/projects/${project.id}/graph`);
  await expect(
    page.getByRole("heading", { name: "Interactive graph" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Accessible graph list" }),
  ).toBeVisible();
  await page.getByLabel("Traversal").selectOption("2");
  await expect(
    page.getByRole("main").locator("p", { hasText: /^2 hops$/ }),
  ).toBeVisible();

  const facts = await apiJson<{
    items: Array<{ status: string; chapter_number: number }>;
  }>(
    request,
    "get",
    `/backend/api/v1/projects/${project.id}/facts?page=1&page_size=100&status=accepted&valid_at_chapter=2`,
  );
  expect(facts.items.every((fact) => fact.status === "accepted")).toBe(true);
  expect(facts.items.every((fact) => fact.chapter_number < 2)).toBe(true);
});

test("filters and resolves a persisted consistency conflict", async ({
  page,
  request,
}) => {
  const { project } = await createAcceptedProject(request, "conflict");
  const conflicts = await apiJson<{
    items: Array<{ id: number; status: string }>;
  }>(
    request,
    "get",
    `/backend/api/v1/projects/${project.id}/conflicts?page=1&page_size=100&status=open`,
  );
  expect(conflicts.items.length).toBeGreaterThan(0);

  await page.goto(`/projects/${project.id}/conflicts`);
  await page.getByLabel("Status").selectOption("open");
  const firstConflict = page.locator("article").first();
  await firstConflict
    .getByLabel("Resolution note")
    .fill("Reviewed in M9 browser acceptance.");
  await firstConflict.getByRole("button", { name: "Resolved" }).click();
  await expect(
    firstConflict.getByText("Resolved", { exact: true }),
  ).toBeVisible();
});
