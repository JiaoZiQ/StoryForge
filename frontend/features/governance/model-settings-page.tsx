"use client";

import { PageHeader, Section } from "@/components/ui/page";
import { ApiErrorAlert, PageLoading } from "@/components/ui/states";
import {
  useModelProfiles,
  useModelSettings,
  useSetModelProfile,
  useSetPrivacyPolicy,
} from "@/hooks/use-storyforge";

export function ModelSettingsPage({ projectId }: { projectId: number }) {
  const settings = useModelSettings(projectId);
  const profiles = useModelProfiles();
  const setProfile = useSetModelProfile(projectId);
  const setPrivacy = useSetPrivacyPolicy(projectId);
  if (settings.isLoading || profiles.isLoading) return <PageLoading />;
  if (settings.error) return <ApiErrorAlert error={settings.error} />;
  if (profiles.error) return <ApiErrorAlert error={profiles.error} />;
  const data = settings.data!;
  return (
    <>
      <PageHeader
        eyebrow={`Project ${projectId}`}
        title="Model settings"
        description="Select predefined routes and enforced data-egress policy. Arbitrary model names and API keys are not accepted here."
      />
      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Model profile">
          <label className="label">
            Profile
            <select
              className="field"
              value={data.model_profile}
              disabled={setProfile.isPending}
              onChange={(event) =>
                setProfile.mutate(
                  event.target.value as
                    "offline" | "economy" | "balanced" | "quality",
                )
              }
            >
              {profiles.data!.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <dl className="mt-4 grid gap-3">
            {profiles.data!.map((item) => (
              <div key={item.name}>
                <dt className="font-bold">{item.name}</dt>
                <dd className="text-sm text-ink-600">{item.description}</dd>
              </div>
            ))}
          </dl>
        </Section>
        <Section title="Privacy policy">
          <label className="label">
            Policy
            <select
              className="field"
              value={data.privacy_policy}
              disabled={setPrivacy.isPending}
              onChange={(event) =>
                setPrivacy.mutate(
                  event.target.value as "offline" | "strict" | "standard",
                )
              }
            >
              <option value="offline">offline — external calls blocked</option>
              <option value="strict">
                strict — minimum context and redaction
              </option>
              <option value="standard">standard — task-required context</option>
            </select>
          </label>
          <p className="mt-4 text-sm text-ink-600">
            Keys remain server-side. Candidate/rejected memory and unrelated
            future reveals are not sent by changing this setting.
          </p>
        </Section>
      </div>
      {setProfile.error || setPrivacy.error ? (
        <div className="mt-5">
          <ApiErrorAlert error={setProfile.error ?? setPrivacy.error} />
        </div>
      ) : null}
    </>
  );
}
