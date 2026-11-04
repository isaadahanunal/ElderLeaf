"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, AUTH_CHANGED, fmt, Irrigation, Plot } from "@/lib/api";
import { firstName, useAuth } from "@/lib/auth";
import { IconAlert, IconCamera, IconCheck, IconChevronRight, IconDroplet, IconPlus } from "@/components/icons";
import { Chip, ErrorBox, LinkButton, Notice, SectionTitle, Skeleton } from "@/components/ui";

const PHOTO_EVERY_DAYS = 6; // a weekly photo keeps the logbook useful

function daysSince(iso: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(`${iso}T12:00:00`).getTime()) / 86_400_000));
}

/** What to do in the garden today: water per plot, plots that need a look, photos that are due. */
export function TodayView() {
  const { me } = useAuth();
  const [plots, setPlots] = useState<Plot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [water, setWater] = useState<Record<string, Irrigation | null>>({});
  const [date, setDate] = useState("");

  const load = useCallback(() => {
    setError(null);
    api.plots().then(setPlots, (e) => setError(e.message));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    window.addEventListener(AUTH_CHANGED, load);
    return () => window.removeEventListener(AUTH_CHANGED, load);
  }, [load]);
  useEffect(() => setDate(new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })), []);

  const own = useMemo(() => plots?.filter((p) => !p.is_demo) ?? [], [plots]);
  const demo = own.length === 0;
  const garden = useMemo(() => (demo ? (plots ?? []).filter((p) => p.is_demo) : own), [demo, plots, own]);
  const ids = garden.map((p) => p.id).join(",");

  useEffect(() => {
    for (const p of garden) {
      api.water(p.id).then(
        (w) => setWater((prev) => ({ ...prev, [p.id]: w })),
        () => setWater((prev) => ({ ...prev, [p.id]: null })),
      );
    }
  }, [ids]); // eslint-disable-line react-hooks/exhaustive-deps

  const needLook = garden.filter((p) => p.attention.length > 0);
  const photoDue = demo ? [] : garden.filter((p) => !p.latest || daysSince(p.latest.captured_at) >= PHOTO_EVERY_DAYS);
  const known = garden.map((p) => water[p.id]).filter((w): w is Irrigation => Boolean(w?.available));
  const total = known.reduce((sum, w) => sum + (w.plot_total_liters ?? 0), 0);
  const loadingWater = garden.some((p) => !(p.id in water));

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[#8a6a35]">{date || " "}</div>
        <h1 className="font-display mt-1 text-[34px] font-semibold leading-tight">{me ? `Today, ${firstName(me.name)}` : "Today in the garden"}</h1>
      </div>

      {error && <ErrorBox message={error} onRetry={load} />}
      {!plots && !error && <Skeleton className="h-56" />}

      {plots && (
        <div className="space-y-8">
          {demo && (
            <Notice tone="info">
              This is the demo garden.{" "}
              <Link href="/new" className="font-semibold underline underline-offset-2">
                Add your own plot
              </Link>{" "}
              to plan your day here.
            </Notice>
          )}

          {/* water */}
          <section className="forest-panel relative overflow-hidden rounded-[28px] p-6">
            <div className="leaf-veins pointer-events-none absolute inset-0" />
            <div className="relative">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#f6efe2]/75">
                <IconDroplet size={16} /> Water today
              </div>
              <div className="mt-2 flex items-end gap-2">
                <span className="tabular text-[48px] font-bold leading-none">{loadingWater && !known.length ? "…" : fmt(total, 0)}</span>
                <span className="pb-1.5 text-lg font-semibold text-[#f6efe2]/75">litres</span>
              </div>
              <p className="mt-1 text-sm text-[#f6efe2]/70">
                {known.length ? `for ${known.length === garden.length ? "your" : `${known.length} of your`} ${known.length === 1 ? "plot" : "plots"}, from today's weather and the cover we measured` : "Take a photo of a plot to get its water need."}
              </p>
              {garden.length > 0 && (
                <ul className="mt-5 divide-y divide-white/10 rounded-2xl bg-white/[0.06] px-4">
                  {garden.map((p) => {
                    const w = water[p.id];
                    return (
                      <li key={p.id} className="flex items-center gap-3 py-3">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[15px] font-semibold">{p.name}</span>
                          <span className="block truncate text-xs text-[#f6efe2]/60">
                            {w === undefined
                              ? "Checking the weather…"
                              : !w?.available
                                ? (w?.reason ?? "No estimate yet")
                                : `${fmt(w.liters_per_m2)} L per m²${w.rain_mm && w.rain_mm >= 1 ? ` · ${fmt(w.rain_mm)} mm rain today` : ""}`}
                          </span>
                        </span>
                        {w?.available && (
                          <span className="tabular shrink-0 text-right text-lg font-bold">
                            {w.plot_total_liters !== null && w.plot_total_liters !== undefined ? `${fmt(w.plot_total_liters, 0)} L` : "–"}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </section>

          {/* needs a look */}
          {needLook.length > 0 && (
            <section>
              <SectionTitle>Needs a look</SectionTitle>
              <div className="space-y-2">
                {needLook.map((p) => (
                  <PlotRow key={p.id} plot={p} href={`/plot?id=${p.id}`}>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {p.attention.map((a) => (
                        <Chip key={a} tone="warn">
                          <IconAlert size={11} /> {a}
                        </Chip>
                      ))}
                    </div>
                  </PlotRow>
                ))}
              </div>
            </section>
          )}

          {/* photos due */}
          {photoDue.length > 0 && (
            <section>
              <SectionTitle>Time for a photo</SectionTitle>
              <div className="space-y-2">
                {photoDue.map((p) => (
                  <PlotRow key={p.id} plot={p} href={`/analyze?plot=${p.id}`} action="Take photo">
                    <div className="mt-0.5 text-xs text-muted">{p.latest ? `Last photo ${daysSince(p.latest.captured_at)} days ago` : "No photo yet"}</div>
                  </PlotRow>
                ))}
              </div>
            </section>
          )}

          {needLook.length === 0 && photoDue.length === 0 && garden.length > 0 && (
            <div className="flex items-center gap-3 rounded-[22px] bg-good-soft px-5 py-4 text-good">
              <IconCheck size={20} strokeWidth={2.6} />
              <span className="text-[15px] font-semibold">All caught up. Nothing else needs you today.</span>
            </div>
          )}

          {garden.length === 0 && (
            <div className="flex flex-col items-center rounded-[28px] border-2 border-dashed border-[#dcd5c8] bg-card/60 px-6 py-12 text-center">
              <p className="font-display text-[22px] font-semibold">Nothing planted yet</p>
              <p className="mt-1 max-w-sm text-sm text-muted">Add a plot and take its first photo. Each day this page tells you how much to water and what to check.</p>
              <LinkButton href="/new" className="mt-5">
                <IconPlus size={16} strokeWidth={2.4} /> New plot
              </LinkButton>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PlotRow({ plot, href, action, children }: { plot: Plot; href: string; action?: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="flex items-center gap-3 rounded-[22px] bg-card p-3 pr-4 shadow-[var(--shadow-card)] transition hover:shadow-md active:scale-[0.99]">
      <span className="h-14 w-14 shrink-0 overflow-hidden rounded-2xl bg-[#e9e4da]">
        {plot.latest && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={plot.latest.image_url} alt="" className="h-full w-full object-cover" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[15px] font-semibold">{plot.name}</span>
        <span className="block truncate text-xs text-muted">
          {plot.crop_label}
          {plot.days_after_planting !== null && ` · day ${plot.days_after_planting}`}
        </span>
        {children}
      </span>
      {action ? (
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-brand px-3 py-2 text-[13px] font-semibold text-white">
          <IconCamera size={14} /> {action}
        </span>
      ) : (
        <IconChevronRight size={16} className="shrink-0 text-muted" />
      )}
    </Link>
  );
}
