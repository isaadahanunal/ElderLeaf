"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, fmt, fmtDate, Plot } from "@/lib/api";
import { IconCamera, IconPlus, IconSprout } from "@/components/icons";
import { Chip, Delta, ErrorBox, LinkButton, METRIC, PageHead, Ring, SectionTitle, Skeleton } from "@/components/ui";

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Good night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function PlotsView() {
  const [plots, setPlots] = useState<Plot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hello, setHello] = useState("Your plots");

  const load = useCallback(() => {
    setError(null);
    api.plots().then(setPlots, (e) => setError(e.message));
  }, []);
  useEffect(load, [load]);
  useEffect(() => setHello(greeting()), []);

  const mine = plots?.filter((p) => !p.is_demo) ?? [];
  const demo = plots?.filter((p) => p.is_demo) ?? [];
  const attention = (plots ?? []).filter((p) => p.attention.length > 0).length;

  return (
    <>
      <PageHead
        title={hello}
        chips={
          plots && (
            <>
              <Chip>
                {plots.length} plot{plots.length === 1 ? "" : "s"}
              </Chip>
              {attention > 0 ? <Chip tone="warn">{attention} need a look</Chip> : <Chip tone="good">All on track</Chip>}
            </>
          )
        }
        actions={
          <LinkButton href="/new">
            <IconPlus size={16} strokeWidth={2.4} /> New plot
          </LinkButton>
        }
      />

      {error && <ErrorBox message={error} onRetry={load} />}
      {!plots && !error && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      )}

      {plots && (
        <div className="space-y-10">
          <section>
            <SectionTitle>My plots</SectionTitle>
            {mine.length ? (
              <PlotGrid plots={mine} />
            ) : (
              <div className="flex flex-col items-center rounded-3xl bg-card px-6 py-12 text-center shadow-[var(--shadow-card)]">
                <span className="grid h-16 w-16 place-items-center rounded-full bg-brand-soft text-brand">
                  <IconSprout size={30} />
                </span>
                <p className="mt-4 text-lg font-bold">Start your first plot</p>
                <p className="mt-1 max-w-sm text-sm text-muted">Snap one photo from above. ElderLeaf counts your plants and tells you if they are on track.</p>
                <LinkButton href="/new" className="mt-5">
                  <IconPlus size={16} strokeWidth={2.4} /> New plot
                </LinkButton>
              </div>
            )}
          </section>
          {demo.length > 0 && (
            <section>
              <SectionTitle right={<span className="text-[13px] text-muted">Read-only · no sign-in</span>}>Demo plots</SectionTitle>
              <PlotGrid plots={demo} />
            </section>
          )}
        </div>
      )}
    </>
  );
}

function PlotGrid({ plots }: { plots: Plot[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {plots.map((p) => (
        <PlotCard key={p.id} plot={p} />
      ))}
    </div>
  );
}

function PlotCard({ plot }: { plot: Plot }) {
  const l = plot.latest;
  return (
    <Link href={`/plot?id=${plot.id}`} className="group block overflow-hidden rounded-3xl bg-card shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-lg">
      <div className="relative aspect-[16/10] bg-[#e6e7eb]">
        {l ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={l.image_url} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
        ) : (
          <div className="grid h-full place-items-center text-muted">
            <span className="flex flex-col items-center gap-2 text-sm">
              <IconCamera size={26} />
              No photo yet
            </span>
          </div>
        )}
        <div className="absolute left-3 top-3 flex gap-1.5">
          {plot.days_after_planting !== null && <span className="rounded-full bg-white/90 px-2.5 py-1 text-xs font-bold backdrop-blur">Day {plot.days_after_planting}</span>}
          {plot.is_demo && <span className="rounded-full bg-ink/80 px-2.5 py-1 text-xs font-bold text-white backdrop-blur">Demo</span>}
        </div>
        {l && <span className="absolute bottom-3 right-3 rounded-full bg-black/55 px-2.5 py-1 text-xs font-semibold text-white backdrop-blur">{fmtDate(l.captured_at)}</span>}
      </div>
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-[17px] font-bold">{plot.name}</h3>
            <p className="text-[13px] text-muted">
              {plot.crop_label}
              {plot.area_m2 ? ` · ${plot.area_m2} m²` : ""}
            </p>
          </div>
          {plot.attention.length > 0 && <Chip tone="warn">{plot.attention[0]}</Chip>}
        </div>
        {l ? (
          <div className="mt-4 grid grid-cols-3 items-center gap-2">
            <div>
              <div className="tabular text-[26px] font-bold leading-none">{fmt(l.plant_count, 0)}</div>
              <div className="mt-1 flex items-center gap-1 text-xs text-muted">
                plants <Delta value={plot.deltas?.plant_count} />
              </div>
            </div>
            <MiniRing label="cover" value={l.canopy_cover_pct} color={METRIC.cover.hex} />
            <MiniRing label="weeds" value={l.weed_share_pct} color={METRIC.weeds.hex} />
          </div>
        ) : (
          <p className="mt-4 text-sm font-semibold text-brand">Take the first photo →</p>
        )}
      </div>
    </Link>
  );
}

function MiniRing({ label, value, color }: { label: string; value: number | null; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <Ring value={value} color={color} size={44} stroke={13} />
      <div>
        <div className="tabular text-[15px] font-bold leading-none">
          {fmt(value)}
          <span className="text-[11px] text-muted">%</span>
        </div>
        <div className="mt-0.5 text-xs text-muted">{label}</div>
      </div>
    </div>
  );
}
