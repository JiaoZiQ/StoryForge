import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-col gap-4 border-b border-black/10 pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow ? (
          <p className="mb-2 text-xs font-black uppercase tracking-[0.18em] text-copper-dark">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 max-w-3xl text-ink-600">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}
export function StatCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: ReactNode;
  detail?: string;
}) {
  return (
    <section className="surface rounded-xl p-5">
      <p className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </p>
      <p className="mt-2 text-3xl font-black">{value}</p>
      {detail ? <p className="mt-2 text-sm text-ink-600">{detail}</p> : null}
    </section>
  );
}
export function Section({
  title,
  children,
  description,
}: {
  title: string;
  children: ReactNode;
  description?: string;
}) {
  return (
    <section className="surface rounded-xl p-5 sm:p-6">
      <h2 className="text-xl font-bold">{title}</h2>
      {description ? (
        <p className="mt-1 text-sm text-ink-600">{description}</p>
      ) : null}
      <div className="mt-5">{children}</div>
    </section>
  );
}
