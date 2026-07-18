import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BudgetPage } from "@/features/governance/budget-page";
import { ModelSettingsPage } from "@/features/governance/model-settings-page";
import { ProvidersPage } from "@/features/governance/providers-page";
import { UsagePage } from "@/features/governance/usage-page";

const hooks = vi.hoisted(() => ({
  useProviders: vi.fn(),
  useProviderHealth: vi.fn(),
  useUsage: vi.fn(),
  useUsageCalls: vi.fn(),
  useBudget: vi.fn(),
  useSetBudget: vi.fn(),
  useModelSettings: vi.fn(),
  useModelProfiles: vi.fn(),
  useSetModelProfile: vi.fn(),
  useSetPrivacyPolicy: vi.fn(),
}));

vi.mock("@/hooks/use-storyforge", () => hooks);

const ready = (data: unknown) => ({ data, isLoading: false, error: null });
const mutation = () => ({
  mutate: vi.fn(),
  isPending: false,
  isSuccess: false,
  error: null,
});

beforeEach(() => {
  hooks.useProviders.mockReturnValue(
    ready([
      {
        provider: "mock",
        model: "mock-storyforge-v1",
        model_type: "chat",
        enabled: true,
        pricing_available: true,
        external: false,
      },
    ]),
  );
  hooks.useProviderHealth.mockReturnValue(
    ready([
      {
        provider: "mock",
        model: "mock-storyforge-v1",
        enabled: true,
        health_status: "healthy",
        circuit_status: "closed",
        pricing_available: true,
        capabilities: ["structured_output"],
      },
    ]),
  );
  hooks.useUsage.mockReturnValue(
    ready({
      calls: 2,
      succeeded: 2,
      failures: 0,
      input_tokens: 100,
      output_tokens: 20,
      cached_input_tokens: 0,
      total_tokens: 120,
      estimated_cost: "0",
      billed_cost: null,
      fallback_count: 0,
      timeout_count: 0,
      rate_limit_count: 0,
      average_latency_ms: "1.5",
      currency: "USD",
    }),
  );
  hooks.useUsageCalls.mockReturnValue(
    ready({
      items: [
        {
          id: 1,
          task_type: "planning",
          provider: "mock",
          model: "mock-storyforge-v1",
          status: "succeeded",
          fallback_index: 0,
          input_tokens: 100,
          output_tokens: 20,
          cached_input_tokens: 0,
          total_tokens: 120,
          usage_source: "mock",
          estimated_cost: "0",
          billed_cost: null,
          currency: "USD",
          latency_ms: 1,
          provider_request_id: null,
          error_code: null,
          created_at: "2026-07-17T00:00:00Z",
          completed_at: "2026-07-17T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 100,
      total: 1,
      pages: 1,
    }),
  );
  hooks.useBudget.mockReturnValue(
    ready({
      project_id: 1,
      currency: "USD",
      soft_limit: "1",
      hard_limit: "2",
      period: "lifetime",
      spent_estimated: "0",
      spent_billed: "0",
      reserved_estimated: "0",
      remaining_estimated: "2",
      alert_thresholds: ["0.5"],
      enabled: true,
    }),
  );
  hooks.useSetBudget.mockReturnValue(mutation());
  hooks.useModelSettings.mockReturnValue(
    ready({
      project_id: 1,
      model_profile: "offline",
      privacy_policy: "offline",
    }),
  );
  hooks.useModelProfiles.mockReturnValue(
    ready([{ name: "offline", description: "Local deterministic providers" }]),
  );
  hooks.useSetModelProfile.mockReturnValue(mutation());
  hooks.useSetPrivacyPolicy.mockReturnValue(mutation());
});

describe("provider governance pages", () => {
  it("renders secret-free providers and content-free usage attempts", () => {
    const { rerender } = render(<ProvidersPage />);
    expect(screen.getByRole("heading", { name: "Providers" })).toBeVisible();
    expect(screen.getByText("mock-storyforge-v1")).toBeVisible();
    rerender(<UsagePage projectId={1} />);
    expect(screen.getByRole("heading", { name: "Usage & cost" })).toBeVisible();
    expect(screen.getAllByText("planning").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/sk-[A-Za-z0-9_-]{12,}/);
  });

  it("renders decimal budget controls and predefined settings", () => {
    const { rerender } = render(<BudgetPage projectId={1} />);
    expect(screen.getByRole("textbox", { name: "Soft limit" })).toHaveValue(
      "1",
    );
    expect(screen.getByRole("button", { name: "Save budget" })).toBeVisible();
    rerender(<ModelSettingsPage projectId={1} />);
    expect(
      screen.getByRole("heading", { name: "Model settings" }),
    ).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Profile" })).toHaveValue(
      "offline",
    );
  });
});
