"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ReactNode, Suspense, useEffect, useState } from "react";
import { api, Plot } from "@/lib/api";
import { IconBook, IconGrid, IconPlus } from "./icons";

export const PLOTS_CHANGED = "elderleaf:plots-changed";

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="" width={40} height={40} className="h-10 w-10 rounded-[11px] shadow-sm" />
      <span className="leading-tight">
        <span className="block text-[17px] font-bold tracking-tight">ElderLeaf</span>
        <span className="block text-[11px] text-muted">An old hand for new growers</span>
      </span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-[272px] shrink-0 flex-col border-r border-line bg-card px-4 py-5 lg:flex">
        <div className="px-2">
          <Logo />
        </div>
        <Suspense>
          <SideNav />
        </Suspense>
      </aside>

      {/* phone / tablet top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-card/90 px-4 pb-2.5 pt-[calc(env(safe-area-inset-top)+0.625rem)] backdrop-blur lg:hidden">
        <Logo />
        <div className="flex items-center gap-1">
          <Link href="/method" className="rounded-full px-3 py-1.5 text-[13px] font-semibold text-ink-2 hover:bg-black/5">
            How it works
          </Link>
          <Link href="/new" aria-label="New plot" className="grid h-9 w-9 place-items-center rounded-full bg-brand text-white">
            <IconPlus size={18} strokeWidth={2.4} />
          </Link>
        </div>
      </header>

      <main className="min-w-0 flex-1 px-4 pb-20 pt-5 sm:px-6 lg:px-10 lg:pt-9">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}

function SideNav() {
  const pathname = usePathname();
  const params = useSearchParams();
  const [plots, setPlots] = useState<Plot[] | null>(null);
  const activePlot = pathname === "/plot" ? params.get("id") : pathname === "/analyze" ? params.get("plot") : null;

  useEffect(() => {
    const load = () => api.plots().then(setPlots, () => setPlots([]));
    load();
    window.addEventListener(PLOTS_CHANGED, load);
    return () => window.removeEventListener(PLOTS_CHANGED, load);
  }, [pathname]);

  const item = (href: string, label: string, icon: ReactNode, active: boolean) => (
    <Link
      href={href}
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-semibold transition ${active ? "bg-brand-soft text-brand" : "text-ink-2 hover:bg-well"}`}
    >
      {icon}
      {label}
    </Link>
  );

  const mine = plots?.filter((p) => !p.is_demo) ?? [];
  const demo = plots?.filter((p) => p.is_demo) ?? [];
  return (
    <>
      <nav className="mt-7 space-y-1">
        {item("/", "All plots", <IconGrid size={18} />, pathname === "/")}
        {item("/new", "New plot", <IconPlus size={18} />, pathname === "/new")}
        {item("/method", "How it works", <IconBook size={18} />, pathname === "/method")}
      </nav>
      <div className="mt-7 min-h-0 flex-1 space-y-5 overflow-y-auto">
        <PlotGroup title="My plots" plots={mine} active={activePlot} empty={plots ? "No plots yet" : "Loading…"} />
        {demo.length > 0 && <PlotGroup title="Demo plots" plots={demo} active={activePlot} />}
      </div>
    </>
  );
}

function PlotGroup({ title, plots, active, empty }: { title: string; plots: Plot[]; active: string | null; empty?: string }) {
  return (
    <div>
      <div className="mb-1.5 px-3 text-[11px] font-bold uppercase tracking-wider text-muted">{title}</div>
      {plots.length === 0 && empty && <div className="px-3 py-1 text-[13px] text-muted">{empty}</div>}
      <ul className="space-y-0.5">
        {plots.map((p) => (
          <li key={p.id}>
            <Link href={`/plot?id=${p.id}`} className={`flex items-center gap-3 rounded-xl px-2 py-2 transition ${active === p.id ? "bg-well" : "hover:bg-well"}`}>
              <span className="h-9 w-9 shrink-0 overflow-hidden rounded-lg bg-[#e6e7eb]">
                {p.latest && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.latest.image_url} alt="" className="h-full w-full object-cover" />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] font-semibold">{p.name}</span>
                <span className="block truncate text-xs text-muted">
                  {p.crop_label}
                  {p.days_after_planting !== null && ` · day ${p.days_after_planting}`}
                </span>
              </span>
              {p.attention.length > 0 && <span className="h-2 w-2 shrink-0 rounded-full bg-[#f59e0b]" title={p.attention.join(", ")} />}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
