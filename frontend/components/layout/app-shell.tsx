"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

const globalLinks = [
  ["Dashboard", "/"],
  ["Projects", "/projects"],
  ["Providers", "/providers"],
  ["System", "/system"],
] as const;
const projectLinks = [
  ["Overview", ""],
  ["Plan", "/plan"],
  ["Chapters", "/chapters"],
  ["Workflow", "/workflow"],
  ["Evaluations", "/evaluations"],
  ["Conflicts", "/conflicts"],
  ["Facts", "/facts"],
  ["Memory", "/memory"],
  ["Retrieval", "/retrieval"],
  ["Graph", "/graph"],
  ["Usage & Cost", "/usage"],
  ["Budget", "/budget"],
  ["Model Settings", "/model-settings"],
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const projectId = pathname.match(/^\/projects\/(\d+)/)?.[1];
  const crumbs = pathname.split("/").filter(Boolean);
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[16rem_1fr]">
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-black/10 bg-ink-950 px-4 py-3 text-white lg:hidden">
        <Link href="/" className="font-bold tracking-wide">
          StoryForge
        </Link>
        <button
          type="button"
          className="rounded border border-white/40 px-3 py-1"
          aria-label="Toggle navigation"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          Menu
        </button>
      </header>
      <aside
        className={`${open ? "block" : "hidden"} bg-ink-950 px-4 py-6 text-white lg:fixed lg:inset-y-0 lg:block lg:w-64 lg:overflow-y-auto`}
      >
        <Link
          href="/"
          className="mb-8 block text-xl font-black tracking-[0.16em]"
        >
          STORYFORGE
        </Link>
        <nav aria-label="Primary navigation" className="grid gap-1">
          {globalLinks.map(([label, href]) => (
            <NavLink
              key={href}
              href={href}
              label={label}
              active={
                href === "/" ? pathname === href : pathname.startsWith(href)
              }
            />
          ))}
        </nav>
        {projectId ? (
          <div className="mt-7 border-t border-white/15 pt-5">
            <p className="mb-2 text-xs font-bold uppercase tracking-widest text-white/55">
              Project {projectId}
            </p>
            <nav aria-label="Project navigation" className="grid gap-1">
              {projectLinks.map(([label, suffix]) => {
                const href = `/projects/${projectId}${suffix}`;
                return (
                  <NavLink
                    key={href}
                    href={href}
                    label={label}
                    active={
                      suffix === ""
                        ? pathname === href
                        : pathname.startsWith(href)
                    }
                  />
                );
              })}
            </nav>
          </div>
        ) : null}
        <p className="mt-8 text-xs text-white/60">
          Local / trusted network only
        </p>
      </aside>
      <div className="min-w-0 lg:col-start-2">
        <div className="border-b border-black/10 bg-white/65 px-5 py-3 backdrop-blur">
          <nav
            aria-label="Breadcrumb"
            className="flex flex-wrap gap-2 text-sm text-ink-600"
          >
            <Link href="/">Home</Link>
            {crumbs.map((crumb, index) => (
              <span key={`${crumb}-${index}`}>
                /{" "}
                <span className="capitalize">{decodeURIComponent(crumb)}</span>
              </span>
            ))}
          </nav>
        </div>
        <main className="mx-auto max-w-[92rem] px-4 py-7 sm:px-6 lg:px-9">
          {children}
        </main>
      </div>
    </div>
  );
}

function NavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded px-3 py-2 text-sm font-semibold ${active ? "bg-copper text-white" : "text-white/75 hover:bg-white/10 hover:text-white"}`}
    >
      {label}
    </Link>
  );
}
