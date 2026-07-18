"use client";

import { PageHeader, Section } from "@/components/ui/page";
import { ErrorState, PageLoading, StatusBadge } from "@/components/ui/states";
import { useProviderHealth, useProviders } from "@/hooks/use-storyforge";

export function ProvidersPage() {
  const providers = useProviders();
  const health = useProviderHealth();
  if (providers.isLoading || health.isLoading) return <PageLoading />;
  if (providers.error) return <ErrorState error={providers.error} />;
  if (health.error) return <ErrorState error={health.error} />;
  return (
    <>
      <PageHeader
        eyebrow="Safe control plane"
        title="Providers"
        description="Registered capabilities and process-local circuit state. Credentials and sensitive endpoint details are never returned."
      />
      <Section title="Registered models">
        <div className="table-wrap">
          <table>
            <caption>Public provider capability registry</caption>
            <thead>
              <tr>
                <th>Provider / model</th>
                <th>Type</th>
                <th>Capabilities</th>
                <th>Pricing</th>
                <th>Health / circuit</th>
              </tr>
            </thead>
            <tbody>
              {providers.data!.map((item) => {
                const state = health.data!.find(
                  (candidate) =>
                    candidate.provider === item.provider &&
                    candidate.model === item.model,
                );
                return (
                  <tr key={`${item.provider}/${item.model}`}>
                    <td>
                      <strong>{item.provider}</strong>
                      <br />
                      <code>{item.model}</code>
                    </td>
                    <td>{item.model_type}</td>
                    <td>{state?.capabilities.join(", ") || "None"}</td>
                    <td>{item.pricing_available ? "Versioned" : "Unknown"}</td>
                    <td>
                      <StatusBadge
                        value={state?.health_status ?? "unavailable"}
                      />{" "}
                      <StatusBadge value={state?.circuit_status ?? "open"} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-sm text-ink-600">
          Health is configuration state, not a billable network probe. Rate
          limits and circuits are local to one server process.
        </p>
      </Section>
    </>
  );
}
