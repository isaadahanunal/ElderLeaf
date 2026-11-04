"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, AUTH_CHANGED, fmt, fmtDate, isNativeApp, Plot } from "@/lib/api";
import { firstName, useAuth } from "@/lib/auth";
import { openCaptureSheet } from "@/components/AppShell";
import { ServerSettings } from "@/components/ServerSettings";
import { IconAlert, IconCamera, IconCheck, IconPlus, IconSprout } from "@/components/icons";
import { Button, Delta, ErrorBox, LinkButton, METRIC, Ring, SectionTitle, Skeleton } from "@/components/ui";

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Good night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function PlotsView() {
  const [plots, setPlots] = useState<Plot[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [hello, setHello] = useState("Hello");

  const load = useCallback(() => {
    setError(null);
    api.plots().then(setPlots, (e) => setError(e));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    window.addEventListener(AUTH_CHANGED, load);
    return () => window.removeEventListener(AUTH_CHANGED, load);
  }, [load]);
  useEffect(() => setHello(greeting()), []);
  const { me, status } = useAuth();

  const mine = plots?.filter((p) => !p.is_demo) ?? [];
  const demo = plots?.filter((p) => p.is_demo) ?? [];

  return (
    <>
      <Hero hello={me ? `${hello}, ${firstName(me.name)}` : hello} gardenName={me?.garden ?? null} plots={plots} />
      {status === "guest" && mine.length > 0 && (
        <Link href="/login?mode=signup" className="fade-in -mt-3 mb-8 flex items-center gap-3 rounded-[22px] border border-gold/40 bg-[#fbf5ea] px-4 py-3 text-sm text-ink-2 transition hover:bg-[#f7eedd]">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gold/20 text-[#8a6a35]">
            <IconSprout size={18} />
          </span>
          <span className="flex-1">
            Your plots live on this phone only. <b className="text-ink">Create an account</b> to keep them and open them anywhere.
          </span>
        </Link>
      )}

      {error && (
        <div className="space-y-4">
          <ErrorBox message={error.message} onRetry={load} />
          {error.status === 0 && isNativeApp() && <ServerSettings onSaved={load} />}
        </div>
      )}
      {!plots && !error && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      )}

      {plots && (
        <div className="space-y-10">
          <section>
            <SectionTitle right={mine.length > 0 && <span className="text-[13px] text-muted">{mine.length} active</span>}>My plots</SectionTitle>
            {mine.length ? (
              <PlotGrid plots={mine} />
            ) : (
              <div className="relative flex flex-col items-center overflow-hidden rounded-[28px] border-2 border-dashed border-[#dcd5c8] bg-card/60 px-6 py-12 text-center">
                <span className="grid h-16 w-16 place-items-center rounded-full bg-brand-soft text-brand">
                  <IconSprout size={30} />
                </span>
                <p className="font-display mt-4 text-[22px] font-semibold">Start your first plot</p>
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

// ------------------------------------------------------------------ hero

function Hero({ hello, gardenName, plots }: { hello: string; gardenName: string | null; plots: Plot[] | null }) {
  // your own plots if you have any, otherwise the demo garden
  const own = plots?.filter((p) => !p.is_demo) ?? [];
  const garden = own.length ? own : (plots ?? []);
  const plants = garden.reduce((n, p) => n + (p.latest?.plant_count ?? p.latest?.row_plant_count ?? 0), 0);
  const attention = garden.filter((p) => p.attention.length > 0).length;
  const last = garden
    .map((p) => p.latest?.captured_at)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(-1);

  return (
    <section className="forest-panel relative -mx-4 mb-8 overflow-hidden px-5 pb-6 pt-7 sm:mx-0 sm:rounded-[32px] sm:px-8 sm:pb-8 sm:pt-9">
      <div className="leaf-veins pointer-events-none absolute inset-0" />
      {/* a garden at dusk: beds in perspective, a few plants outlined like SAM masks with their ids.
          Phone: a band above the text. Wider screens: behind the text, on the right. */}
      <div aria-hidden="true" className="hero-band relative -mx-5 -mt-7 -mb-3 sm:hidden" />
      <div aria-hidden="true" className="hero-art pointer-events-none absolute inset-0 hidden sm:block" />
      <div className="relative">
        <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-gold">{gardenName ?? (own.length ? "Your garden" : "Welcome to ElderLeaf")}</div>
        <h1 className="font-display mt-2 text-[38px] font-semibold leading-[1.05] sm:text-[48px]">{hello}</h1>
        <p className="mt-2 max-w-md text-[15px] leading-relaxed text-[#f6efe2]/80">
          {own.length
            ? attention > 0
              ? `${attention} of your plots could use a look this week.`
              : "Everything you measured looks on track."
            : "Walk to a plot, take one photo from above, and see every plant counted, with its mask."}
        </p>

        <div className="mt-5 flex flex-wrap gap-2.5">
          <Button variant="gold" size="lg" onClick={openCaptureSheet}>
            <IconCamera size={18} /> Analyze a plot
          </Button>
          <LinkButton href="/new" variant="glass" size="lg">
            <IconPlus size={17} strokeWidth={2.3} /> New plot
          </LinkButton>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-2 sm:max-w-lg">
          <HeroStat value={plots ? String(garden.length) : "–"} label={garden.length === 1 ? "plot" : "plots"} />
          <HeroStat value={plots ? String(plants) : "–"} label="plants counted" />
          <HeroStat
            value={plots ? (attention > 0 ? String(attention) : "") : "–"}
            icon={plots && attention === 0 ? <IconCheck size={20} strokeWidth={2.6} /> : plots && attention > 0 ? <IconAlert size={18} /> : null}
            label={attention > 0 ? "need a look" : "on track"}
            warn={attention > 0}
          />
        </div>
        {last && <div className="mt-3 text-xs text-[#f6efe2]/55">Last measured {fmtDate(last)}</div>}
      </div>
    </section>
  );
}

function HeroStat({ value, label, icon, warn }: { value: string; label: string; icon?: React.ReactNode; warn?: boolean }) {
  return (
    <div className="glass rounded-2xl !bg-[#0f1d17]/45 px-3 py-2.5">
      <div className={`tabular flex items-center gap-1 text-[24px] font-bold leading-none ${warn ? "text-gold" : ""}`}>
        {icon}
        {value}
      </div>
      <div className="mt-1 text-[11px] font-medium text-[#f6efe2]/65">{label}</div>
    </div>
  );
}

// ------------------------------------------------------------------ cards

function PlotGrid({ plots }: { plots: Plot[] }) {
  return (
    <div className="stagger grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {plots.map((p) => (
        <PlotCard key={p.id} plot={p} />
      ))}
    </div>
  );
}

function PlotCard({ plot }: { plot: Plot }) {
  const l = plot.latest;
  const video = l?.mode === "video";
  return (
    <Link href={`/plot?id=${plot.id}`} className="group block overflow-hidden rounded-[26px] bg-card shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)] active:scale-[0.99]">
      <div className="relative aspect-[16/11] bg-[#e9e4da]">
        {l ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={l.image_url} alt="" className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.04]" />
        ) : (
          <div className="grid h-full place-items-center bg-gradient-to-br from-[#ebe7de] to-[#e0d9cb] text-muted">
            <span className="flex flex-col items-center gap-2 text-sm">
              <IconCamera size={26} />
              No photo yet
            </span>
          </div>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-[#0c1511]/80 via-[#0c1511]/25 to-transparent" />
        <div className="absolute left-3 top-3 flex gap-1.5">
          {plot.days_after_planting !== null && <span className="rounded-full bg-white/90 px-2.5 py-1 text-xs font-bold backdrop-blur">Day {plot.days_after_planting}</span>}
          {plot.is_demo && <span className="rounded-full bg-forest/80 px-2.5 py-1 text-xs font-bold text-[#f6efe2] backdrop-blur">Demo</span>}
        </div>
        {plot.attention.length > 0 && (
          <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-gold px-2.5 py-1 text-xs font-bold text-forest shadow">
            <IconAlert size={12} /> {plot.attention[0]}
          </span>
        )}
        <div className="absolute inset-x-4 bottom-3.5 flex items-end justify-between gap-3 text-white">
          <div className="min-w-0">
            <h3 className="font-display truncate text-[22px] font-semibold leading-tight">{plot.name}</h3>
            <p className="text-[13px] text-white/75">
              {plot.crop_label}
              {plot.area_m2 ? ` · ${plot.area_m2} m²` : ""}
            </p>
          </div>
          {l && <span className="shrink-0 text-xs font-semibold text-white/80">{fmtDate(l.captured_at)}</span>}
        </div>
      </div>
      <div className="px-5 py-4">
        {l && !video ? (
          <div className="grid grid-cols-3 items-center gap-2">
            <div>
              <div className="tabular text-[28px] font-bold leading-none">{fmt(l.plant_count, 0)}</div>
              <div className="mt-1 flex items-center gap-1 text-xs text-muted">
                plants <Delta value={plot.deltas?.plant_count} />
              </div>
            </div>
            <MiniRing label="cover" value={l.canopy_cover_pct} color={METRIC.cover.hex} />
            <MiniRing label="weeds" value={l.weed_share_pct} color={METRIC.weeds.hex} />
          </div>
        ) : l && video ? (
          <div className="flex items-center gap-3">
            <div className="tabular text-[28px] font-bold leading-none">{l.row_plant_count ?? "–"}</div>
            <div className="text-xs text-muted">plants in the row, counted from a walking video</div>
          </div>
        ) : (
          <p className="flex items-center gap-1.5 text-sm font-semibold text-brand">
            <IconCamera size={15} /> Take the first photo
          </p>
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

