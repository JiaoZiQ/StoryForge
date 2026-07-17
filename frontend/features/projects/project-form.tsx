"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useForm, type UseFormReturn } from "react-hook-form";
import { z } from "zod";
import { ApiClientError } from "@/lib/api/errors";
import { useCreateProject } from "@/hooks/use-storyforge";
import { ApiErrorAlert, InlineLoading } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page";

export const projectFormSchema = z.object({
  title: z.string().trim().min(1).max(200),
  genre: z.string().trim().min(1).max(100),
  premise: z.string().trim().min(1).max(20000),
  target_chapters: z.coerce.number().int().min(1).max(1000),
  target_words_per_chapter: z.coerce.number().int().min(50).max(100000),
  language: z.string().trim().min(2).max(32),
  tone: z.string().trim().max(100).optional(),
  audience: z.string().trim().max(100).optional(),
  additional_requirements: z.string().max(10000),
});
type ProjectFormInput = z.input<typeof projectFormSchema>;
type ProjectFormValues = z.output<typeof projectFormSchema>;

export function ProjectForm() {
  const router = useRouter();
  const mutation = useCreateProject();
  const form = useForm<ProjectFormInput, unknown, ProjectFormValues>({
    resolver: zodResolver(projectFormSchema),
    defaultValues: {
      title: "",
      genre: "",
      premise: "",
      target_chapters: 3,
      target_words_per_chapter: 1200,
      language: "zh-CN",
      tone: "",
      audience: "",
      additional_requirements: "",
    },
  });
  const submit = form.handleSubmit(async (values) => {
    try {
      const project = await mutation.mutateAsync({
        ...values,
        tone: values.tone || null,
        audience: values.audience || null,
      });
      router.push(`/projects/${project.id}`);
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 422) {
        for (const detail of error.details) {
          if (detail.field && detail.field in values)
            form.setError(detail.field as keyof ProjectFormValues, {
              type: "server",
              message: detail.message,
            });
        }
      }
    }
  });
  return (
    <>
      <PageHeader
        eyebrow="New story"
        title="Create a project"
        description="Define the durable brief. Story generation remains on the server and the browser stores no provider keys."
      />
      <form
        className="surface grid gap-5 rounded-xl p-5 sm:grid-cols-2 sm:p-7"
        onSubmit={submit}
        noValidate
      >
        {mutation.error ? (
          <div className="sm:col-span-2">
            <ApiErrorAlert error={mutation.error} />
          </div>
        ) : null}
        <Field form={form} name="title" label="Title" />
        <Field form={form} name="genre" label="Genre" />
        <label className="label sm:col-span-2">
          Premise
          <textarea
            className="field min-h-32"
            {...form.register("premise")}
            aria-invalid={Boolean(form.formState.errors.premise)}
            aria-describedby="premise-error"
          />
          {form.formState.errors.premise ? (
            <span
              id="premise-error"
              role="alert"
              className="text-sm text-red-800"
            >
              {form.formState.errors.premise.message}
            </span>
          ) : null}
        </label>
        <Field
          form={form}
          name="target_chapters"
          label="Target chapters"
          type="number"
        />
        <Field
          form={form}
          name="target_words_per_chapter"
          label="Target words per chapter"
          type="number"
        />
        <Field form={form} name="language" label="Language" />
        <Field form={form} name="tone" label="Tone" />
        <Field form={form} name="audience" label="Audience" />
        <label className="label sm:col-span-2">
          Additional requirements
          <textarea
            className="field min-h-24"
            {...form.register("additional_requirements")}
            aria-invalid={Boolean(
              form.formState.errors.additional_requirements,
            )}
          />
        </label>
        <div className="flex items-center gap-3 sm:col-span-2">
          <button
            className="button-primary"
            type="submit"
            disabled={form.formState.isSubmitting || mutation.isPending}
          >
            {mutation.isPending ? "Creating…" : "Create project"}
          </button>
          {mutation.isPending ? (
            <InlineLoading label="Creating project…" />
          ) : null}
        </div>
      </form>
    </>
  );
}

function Field({
  form,
  name,
  label,
  type = "text",
}: {
  form: UseFormReturn<ProjectFormInput, unknown, ProjectFormValues>;
  name: keyof ProjectFormInput;
  label: string;
  type?: string;
}) {
  const error = form.formState.errors[name];
  return (
    <label className="label">
      {label}
      <input
        className="field"
        type={type}
        {...form.register(name)}
        aria-invalid={Boolean(error)}
        aria-describedby={`${name}-error`}
      />
      {error ? (
        <span
          id={`${name}-error`}
          role="alert"
          className="text-sm text-red-800"
        >
          {error.message}
        </span>
      ) : null}
    </label>
  );
}
