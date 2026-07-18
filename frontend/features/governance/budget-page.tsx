"use client";

import { useState } from "react";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import { ApiErrorAlert, PageLoading } from "@/components/ui/states";
import { useBudget, useSetBudget, useUsageCalls } from "@/hooks/use-storyforge";

export function BudgetPage({ projectId }: { projectId: number }) {
  const budget = useBudget(projectId);
  const calls = useUsageCalls(projectId);
  const update = useSetBudget(projectId);
  if (budget.isLoading || calls.isLoading) return <PageLoading />;
  if (budget.error) return <ApiErrorAlert error={budget.error} />;
  if (calls.error) return <ApiErrorAlert error={calls.error} />;
  const data = budget.data!;
  const blocked = calls.data!.items.filter(
    (item) => item.status === "budget_blocked",
  ).length;
  return (
    <>
      <PageHeader
        eyebrow={`Project ${projectId}`}
        title="Budget"
        description="Hard limits reserve estimated cost before a provider call. Soft limits warn without blocking."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label="Estimated spent"
          value={`${data.currency} ${data.spent_estimated}`}
        />
        <StatCard
          label="Billed spent"
          value={`${data.currency} ${data.spent_billed}`}
        />
        <StatCard
          label="Reserved"
          value={`${data.currency} ${data.reserved_estimated}`}
        />
        <StatCard
          label="Estimated remaining"
          value={`${data.currency} ${data.remaining_estimated}`}
        />
        <StatCard
          label="Blocked calls"
          value={blocked}
          detail={`Thresholds: ${data.alert_thresholds.join(", ") || "none"}`}
        />
      </div>
      <div className="mt-6 max-w-2xl">
        <Section
          title="Lifetime limits"
          description="Amounts remain decimal strings end to end; clients cannot write spent values."
        >
          <BudgetForm
            key={`${data.soft_limit}/${data.hard_limit}`}
            initialSoft={data.soft_limit}
            initialHard={data.hard_limit}
            pending={update.isPending}
            onSave={(soft, hard) =>
              update.mutate({
                currency: data.currency,
                soft_limit: soft,
                hard_limit: hard,
                period: "lifetime",
                enabled: data.enabled,
              })
            }
          />
          {update.error ? (
            <div className="mt-4">
              <ApiErrorAlert error={update.error} />
            </div>
          ) : null}
          {update.isSuccess ? (
            <p role="status" className="mt-4 text-teal-dark">
              Budget saved.
            </p>
          ) : null}
        </Section>
      </div>
    </>
  );
}

function BudgetForm({
  initialSoft,
  initialHard,
  pending,
  onSave,
}: {
  initialSoft: string;
  initialHard: string;
  pending: boolean;
  onSave: (soft: string, hard: string) => void;
}) {
  const [soft, setSoft] = useState(initialSoft);
  const [hard, setHard] = useState(initialHard);
  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(soft, hard);
      }}
    >
      <label className="label">
        Soft limit
        <input
          className="field"
          inputMode="decimal"
          required
          value={soft}
          onChange={(event) => setSoft(event.target.value)}
        />
      </label>
      <label className="label">
        Hard limit
        <input
          className="field"
          inputMode="decimal"
          required
          value={hard}
          onChange={(event) => setHard(event.target.value)}
        />
      </label>
      <button className="button-primary" type="submit" disabled={pending}>
        {pending ? "Saving…" : "Save budget"}
      </button>
    </form>
  );
}
