"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AnalysisOut, AnalysisSummary, api, CompareOut, fmt, fmtDate, Irrigation, Note, PlotDetail, today } from "@/lib/api";
import { MaskOverlay } from "@/components/MaskOverlay";
import { AssistantCard, assistantText, CoverCard, PlantsCard, WaterCard, WeedsCard, weedFlag } from "@/components/MetricCards";
import { Sheet } from "@/components/Sheet";
import { TrendCharts } from "@/components/TrendCharts";
import { IconCamera, IconChevronRight, IconDownload, IconDroplet, IconNote } from "@/components/icons";
import {
  BackLink,
  Button,
  Card,
  Chip,
  Delta,
  ErrorBox,
  inputClass,
  LinkButton,
  METRIC,
  MetricKey,
  PageHead,
  Segmented,
  SectionTitle,
  Skeleton,
  Spinner,
} from "@/components/ui";

type Tab = "overview" | "logbook" | "compare";

export function PlotView() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id") ?? "";
  const tab = (["overview", "logbook", "compare"].includes(params.get("tab") ?? "") ? params.get("tab") : "overview") as Tab;
  const [plot, setPlot] = useState<PlotDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api.plot(id).then(setPlot, (e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  const setTab = (t: string) => router.replace(`/plot?id=${id}${t === "overview" ? "" : `&tab=${t}`}`, { scroll: false });

  if (error)
    return (
      <>
        <BackLink href="/" label="All plots" />
        <ErrorBox message={error} onRetry={load} />
      </>
    );
  if (!plot)
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-80" />
      </div>
    );

  const photos = plot.analyses.filter((a) => a.status === "done");
  const cover = photos.at(-1)?.image_url ?? plot.latest?.image_url;
  const meta = [
    plot.crop_label,
    plot.days_after_planting !== null ? `day ${plot.days_after_planting}` : null,
    plot.area_m2 ? `${plot.area_m2} m²` : null,
    plot.planted_on ? `planted ${fmtDate(plot.planted_on)}` : null,
  ].filter(Boolean);
  return (
    <>
      {/* cover: the latest photo with the plot's name on it */}
      <section className="relative -mx-4 -mt-5 overflow-hidden bg-forest sm:mx-0 sm:mt-0 sm:rounded-[32px]">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cover} alt="" className="h-[270px] w-full object-cover sm:h-[320px]" />
        ) : (
          <div className="forest-panel h-[220px] w-full">
            <div className="leaf-veins h-full w-full" />
          </div>
        )}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#0c1511]/90 via-[#0c1511]/30 to-[#0c1511]/10" />
        <Link href="/" aria-label="All plots" className="glass absolute left-4 top-4 grid h-10 w-10 place-items-center rounded-full text-white">
          <IconChevronRight size={18} className="rotate-180" />
        </Link>
        {plot.is_demo && <span className="glass absolute right-4 top-4 rounded-full px-3 py-1.5 text-xs font-semibold text-white">Demo · read-only</span>}
        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-3 px-5 pb-5 sm:flex-row sm:items-end sm:justify-between sm:px-7 sm:pb-6">
          <div className="min-w-0 text-white">
            <h1 className="font-display line-clamp-2 text-[32px] font-semibold leading-[1.05] sm:text-[38px]">{plot.name}</h1>
            <p className="mt-1.5 text-sm text-white/75">{meta.join(" · ")}</p>
          </div>
          {!plot.is_demo && (
            <div className="flex shrink-0 gap-2">
              <LinkButton href={`/analyze?plot=${plot.id}`} variant="gold">
                <IconCamera size={16} /> Take photo
              </LinkButton>
            </div>
          )}
        </div>
      </section>

      {/* tabs stay in reach while you scroll */}
      <div className="sticky top-[calc(env(safe-area-inset-top)+61px)] z-20 -mx-4 mb-6 bg-canvas/90 px-4 py-3 backdrop-blur-xl lg:top-0 lg:mx-0 lg:px-0">
        <Segmented
          options={[
            { id: "overview", label: "Overview" },
            { id: "logbook", label: `Logbook · ${plot.analyses.length + plot.notes.length}` },
            { id: "compare", label: "Compare" },
          ]}
          value={tab}
          onChange={setTab}
        />
      </div>
      <div className="fade-in" key={tab}>
        {tab === "overview" && <Overview plot={plot} />}
        {tab === "logbook" && <Logbook plot={plot} onChange={load} />}
        {tab === "compare" &&
          (photos.length >= 2 ? (
            <Compare plot={plot} photos={photos} />
          ) : (
            <Empty title="Compare needs two photos" text={plot.is_demo ? "This plot has one photo so far." : "Take another photo from the same spot in a few days."} />
          ))}
      </div>
    </>
  );
}

function Empty({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-3xl bg-card px-6 py-14 text-center shadow-[var(--shadow-card)]">
      <span className="grid h-14 w-14 place-items-center rounded-full bg-brand-soft text-brand">
        <IconCamera size={26} />
      </span>
      <p className="mt-4 text-lg font-bold">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-muted">{text}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ overview

function Overview({ plot }: { plot: PlotDetail }) {
  const photos = plot.analyses.filter((a) => a.status === "done");
  const latestPhoto = photos.at(-1);
  const [latest, setLatest] = useState<AnalysisOut | null>(null);
  const [water, setWater] = useState<Irrigation | null | undefined>(undefined);

  useEffect(() => {
    if (latestPhoto) api.analysis(latestPhoto.id).then(setLatest, () => setLatest(null));
  }, [latestPhoto?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.water(plot.id).then(setWater, () => setWater(null));
  }, [plot.id]);

  if (!plot.analyses.length)
    return (
      <Empty
        title="No photos yet"
        text="Take one photo of the plot from above. ElderLeaf counts the plants, measures cover and weeds, and starts this logbook."
        action={
          !plot.is_demo && (
            <LinkButton href={`/analyze?plot=${plot.id}`}>
              <IconCamera size={16} /> Analyze photo
            </LinkButton>
          )
        }
      />
    );

  const r = latest?.result;
  const l = plot.latest;
  return (
    <div className="space-y-8">
      {latestPhoto && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
          <div className="relative">
            {r && latest ? (
              <MaskOverlay imageUrl={latest.image_url} width={r.image.width} height={r.image.height} masks={r.masks} visible={new Set(["crop", "weed", "lesion"])} />
            ) : (
              <Skeleton className="aspect-[4/3]" />
            )}
            <span className="absolute left-3 top-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold backdrop-blur">Latest · {fmtDate(latestPhoto.captured_at)}</span>
            <Link
              href={`/analysis?id=${latestPhoto.id}`}
              className="absolute bottom-3 right-3 inline-flex items-center gap-1 rounded-full bg-white/95 px-3.5 py-2 text-[13px] font-semibold shadow-lg backdrop-blur hover:bg-white"
            >
              Open analysis <IconChevronRight size={14} />
            </Link>
          </div>
          {!r ? <Skeleton className="h-64" /> : assistantText(r) ? <AssistantCard s={assistantText(r)!} consult={r.health.consult_agronomist} /> : <div />}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <PlantsCard value={l?.plant_count ?? null} delta={plot.deltas?.plant_count} history={photos.map((a) => a.plant_count)} how={r?.metrics.plant_count.how} />
        <CoverCard
          value={l?.canopy_cover_pct ?? null}
          delta={plot.deltas?.canopy_cover_pct}
          band={r?.crop_info?.cover_typical_pct ?? null}
          day={r?.days_after_planting}
          how={r?.metrics.canopy_cover_pct.how}
        />
        <WeedsCard value={l?.weed_share_pct ?? null} delta={plot.deltas?.weed_share_pct} flag={weedFlag(r)} how={r?.metrics.weed_share_pct.how} />
        <WaterCard w={water} />
      </div>

      <section>
        <SectionTitle>Trends</SectionTitle>
        <TrendCharts analyses={plot.analyses} />
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ logbook

const NOTE_KINDS: { id: string; label: string; m: MetricKey }[] = [
  { id: "watering", label: "Watering", m: "water" },
  { id: "fertilizer", label: "Fertilizer", m: "plants" },
  { id: "spraying", label: "Spraying", m: "health" },
  { id: "observation", label: "Observation", m: "cover" },
  { id: "other", label: "Other", m: "size" },
];

type Row = { type: "analysis"; date: string; a: AnalysisSummary } | { type: "note"; date: string; n: Note };

function Logbook({ plot, onChange }: { plot: PlotDetail; onChange: () => void }) {
  const [noteOpen, setNoteOpen] = useState(false);
  const rows = useMemo(() => {
    const items: Row[] = [
      ...plot.analyses.map((a) => ({ type: "analysis" as const, date: a.captured_at, a })),
      ...plot.notes.map((n) => ({ type: "note" as const, date: n.date, n })),
    ];
    return items.sort((x, y) => (x.date < y.date ? 1 : x.date > y.date ? -1 : x.type === "note" ? 1 : -1));
  }, [plot]);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="order-2 space-y-3 lg:order-1">
        {rows.length === 0 && <p className="text-sm text-muted">Nothing here yet.</p>}
        {rows.map((row) => (row.type === "analysis" ? <EntryCard key={row.a.id} a={row.a} /> : <NoteCard key={row.n.id} n={row.n} />))}
      </div>
      <div className="order-1 flex gap-2 lg:order-2 lg:flex-col">
        {!plot.is_demo && (
          <Button onClick={() => setNoteOpen(true)} className="flex-1 lg:flex-none">
            <IconNote size={16} /> Add a note
          </Button>
        )}
        <LinkButton href={api.csvUrl(plot.id)} external variant="white" className="flex-1 lg:flex-none">
          <IconDownload size={16} /> Export CSV
        </LinkButton>
      </div>
      <Sheet open={noteOpen} onClose={() => setNoteOpen(false)} title="Add a note" subtitle="Watering, fertilizer, spraying or what you saw">
        <NoteForm
          plotId={plot.id}
          bare
          onSaved={() => {
            setNoteOpen(false);
            onChange();
          }}
        />
      </Sheet>
    </div>
  );
}

function EntryCard({ a }: { a: AnalysisSummary }) {
  const running = a.status === "pending" || a.status === "running";
  return (
    <Link href={`/analysis?id=${a.id}`} className="flex gap-4 rounded-2xl bg-card p-3 pr-4 shadow-[var(--shadow-card)] transition hover:shadow-md">
      <div className="relative h-20 w-24 shrink-0 overflow-hidden rounded-xl bg-[#e9e4da]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={a.image_url} alt="" className="h-full w-full object-cover" />
        <span className="absolute bottom-1 left-1 grid h-6 w-6 place-items-center rounded-full bg-white/90 text-ink"><IconCamera size={13} /></span>
      </div>
      <div className="min-w-0 flex-1 py-0.5">
        <div className="flex items-center justify-between gap-2">
          <span className="font-bold">{fmtDate(a.captured_at)}</span>
          {running && (
            <span className="flex items-center gap-1.5 text-xs text-muted">
              <Spinner className="h-3 w-3" /> Analysing
            </span>
          )}
          {a.status === "failed" && <Chip tone="warn">Failed</Chip>}
        </div>
        {a.status === "done" && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Stat m="plants" text={`${fmt(a.plant_count, 0)} plants`} />
            <Stat m="cover" text={`${fmt(a.canopy_cover_pct)}% cover`} />
            <Stat m="weeds" text={`${fmt(a.weed_share_pct)}% weeds`} />
          </div>
        )}
        {a.attention.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {a.attention.map((t) => (
              <Chip key={t} tone="warn">
                {t}
              </Chip>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

function Stat({ m, text }: { m: MetricKey; text: string }) {
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-well px-2.5 text-xs font-semibold text-ink-2">
      <span className="h-2 w-2 rounded-full" style={{ background: METRIC[m].hex }} />
      {text}
    </span>
  );
}

function NoteCard({ n }: { n: Note }) {
  const kind = NOTE_KINDS.find((k) => k.id === n.kind) ?? NOTE_KINDS[4];
  const { hex } = METRIC[kind.m];
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-dashed border-[#dcd5c8] px-4 py-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full" style={{ background: `${hex}1a`, color: hex }}>
        {n.kind === "watering" ? <IconDroplet size={18} /> : <IconNote size={18} />}
      </span>
      <div className="min-w-0">
        <div className="text-xs font-semibold text-muted">
          {fmtDate(n.date)} · {kind.label}
        </div>
        <p className="text-sm text-ink">{n.text}</p>
      </div>
    </div>
  );
}

function NoteForm({ plotId, onSaved, bare = false }: { plotId: string; onSaved: () => void; bare?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState("watering");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    setError(null);
    try {
      await api.addNote(plotId, { kind, date: String(f.get("date")), text: String(f.get("text")) });
      form.reset();
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const form = (
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {NOTE_KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              onClick={() => setKind(k.id)}
              className={`h-8 rounded-full px-3 text-[13px] font-semibold transition ${kind === k.id ? "bg-ink text-white" : "bg-well text-ink-2 hover:bg-[#ebe7de]"}`}
            >
              {k.label}
            </button>
          ))}
        </div>
        <input name="text" required maxLength={2000} placeholder="Watered about 10 L in the evening" className={inputClass} />
        <div className="flex gap-2">
          <input name="date" type="date" defaultValue={today()} max={today()} required className={`${inputClass} flex-1`} />
          <Button type="submit" disabled={busy}>
            {busy && <Spinner />} Save
          </Button>
        </div>
        {error && <ErrorBox message={error} />}
      </form>
  );
  if (bare) return form;
  return (
    <Card>
      <div className="mb-3 text-[15px] font-bold">Add a note</div>
      {form}
    </Card>
  );
}

// ------------------------------------------------------------------ compare

const COMPARE_META: Record<string, MetricKey> = {
  plant_count: "plants",
  canopy_cover_pct: "cover",
  weed_share_pct: "weeds",
  lesion_share_pct: "spots",
  mean_plant_area: "size",
};

function Compare({ plot, photos }: { plot: PlotDetail; photos: AnalysisSummary[] }) {
  const [aId, setAId] = useState(photos[0].id);
  const [bId, setBId] = useState(photos[photos.length - 1].id);
  const [cmp, setCmp] = useState<CompareOut | null>(null);
  const [full, setFull] = useState<Record<string, AnalysisOut>>({});
  const [error, setError] = useState<string | null>(null);
  const [pos, setPos] = useState(50);

  useEffect(() => {
    if (aId === bId) return;
    setCmp(null);
    setError(null);
    api.compare(plot.id, aId, bId).then(setCmp, (e) => setError(e.message));
    for (const x of [aId, bId]) {
      if (!full[x]) api.analysis(x).then((r) => setFull((f) => ({ ...f, [x]: r })));
    }
  }, [aId, bId, plot.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // a tapped photo replaces the nearer of the two dates, so "before" always stays older than "after"
  function pick(id: string) {
    const i = photos.findIndex((p) => p.id === id);
    const ia = photos.findIndex((p) => p.id === aId);
    const ib = photos.findIndex((p) => p.id === bId);
    if (i === ia || i === ib) return;
    if (i < ia || (i < ib && i - ia <= ib - i)) setAId(id);
    else setBId(id);
  }

  const older = cmp ? full[cmp.before.analysis_id] : undefined;
  const newer = cmp ? full[cmp.after.analysis_id] : undefined;
  const visible = useMemo(() => new Set(["crop", "weed", "lesion"]), []);

  return (
    <div className="space-y-4">
      <PhotoStrip photos={photos} before={aId} after={bId} onPick={pick} />
      <p className="text-[13px] text-muted">
        {cmp ? `${cmp.days_between} days apart. ` : ""}
        {photos.length > 2 ? "Tap a photo to compare it." : ""}
      </p>
      {error && <ErrorBox message={error} />}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <div>
          {older?.result && newer?.result && cmp ? (
            <div className="relative w-full overflow-hidden rounded-2xl" style={{ aspectRatio: `${newer.result.image.width} / ${newer.result.image.height}` }}>
              <div className="absolute inset-0">
                <MaskOverlay fill rounded={false} imageUrl={newer.image_url} width={newer.result.image.width} height={newer.result.image.height} masks={newer.result.masks} visible={visible} />
              </div>
              <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
                <MaskOverlay fill rounded={false} imageUrl={older.image_url} width={older.result.image.width} height={older.result.image.height} masks={older.result.masks} visible={visible} />
              </div>
              <div className="pointer-events-none absolute inset-y-0 w-1 -translate-x-1/2 bg-white shadow-[0_0_8px_rgba(0,0,0,0.35)]" style={{ left: `${pos}%` }}>
                <span className="absolute left-1/2 top-1/2 grid h-10 w-10 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-white text-ink shadow-lg">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M9 7l-5 5 5 5M15 7l5 5-5 5" />
                  </svg>
                </span>
              </div>
              <span className="absolute left-3 top-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold">{fmtDate(cmp.before.captured_at)}</span>
              <span className="absolute right-3 top-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold">{fmtDate(cmp.after.captured_at)}</span>
              <input
                type="range"
                min={0}
                max={100}
                value={pos}
                onChange={(e) => setPos(Number(e.target.value))}
                aria-label="Compare slider"
                className="compare-slider absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
              />
            </div>
          ) : (
            aId !== bId && !error && <Skeleton className="aspect-[4/3]" />
          )}
        </div>
        {cmp && (
          <div className="space-y-4">
            <Card>
              <div className="mb-1 text-[15px] font-bold">What changed</div>
              <div className="divide-y divide-line">
                {cmp.rows
                  .filter((r) => r.before !== null || r.after !== null)
                  .map((r) => {
                    const m = COMPARE_META[r.metric] ?? "plants";
                    const u = r.unit === "cm2" ? " cm²" : r.unit === "%" ? "%" : r.unit === "px" ? " px" : "";
                    const max = Math.max(r.before ?? 0, r.after ?? 0, 1e-9);
                    return (
                      <div key={r.metric} className="py-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-2 text-sm font-semibold text-ink-2">
                            <span className="h-2.5 w-2.5 rounded-full" style={{ background: METRIC[m].hex }} />
                            {r.label}
                          </span>
                          <span className="flex items-center gap-2">
                            <span className="tabular text-sm font-bold">
                              {r.after === null ? "–" : `${fmt(r.after)}${u}`}
                            </span>
                            <Delta value={r.change} unit={u === "%" ? " pts" : ""} invert={r.metric === "weed_share_pct" || r.metric === "lesion_share_pct"} />
                          </span>
                        </div>
                        <div className="mt-2 space-y-1">
                          <div className="h-1.5 rounded-full bg-[#efebe3]">
                            <div className="h-1.5 rounded-full bg-[#c9ccd3]" style={{ width: `${((r.before ?? 0) / max) * 100}%` }} />
                          </div>
                          <div className="h-1.5 rounded-full bg-[#efebe3]">
                            <div className="h-1.5 rounded-full" style={{ width: `${((r.after ?? 0) / max) * 100}%`, background: METRIC[m].hex }} />
                          </div>
                        </div>
                      </div>
                    );
                  })}
              </div>
              <div className="mt-2 flex gap-4 text-xs text-muted">
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-4 rounded-full bg-[#c9ccd3]" /> {fmtDate(cmp.before.captured_at)}
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-4 rounded-full bg-ink" /> {fmtDate(cmp.after.captured_at)}
                </span>
              </div>
            </Card>
          </div>
        )}
      </div>
      {cmp && (
        <div className="grid gap-4 lg:grid-cols-2">
          <AssistantCard s={{ text: cmp.summary, next_step: cmp.next_step, source: cmp.written_by, attempts: cmp.validator.attempts, validator_issues: [], error: null }} title="Change summary" compact />
          {cmp.notes.length > 0 && (
            <Card>
              <div className="mb-3 text-[15px] font-bold">Your notes in between</div>
              <div className="space-y-2">
                {cmp.notes.map((n) => (
                  <NoteCard key={n.id} n={n} />
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

function PhotoStrip({ photos, before, after, onPick }: { photos: AnalysisSummary[]; before: string; after: string; onPick: (id: string) => void }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 pb-1 lg:mx-0 lg:px-0">
      <div className="flex gap-3">
        {photos.map((p) => {
          const role = p.id === before ? "Before" : p.id === after ? "After" : null;
          return (
            <button key={p.id} type="button" onClick={() => onPick(p.id)} aria-pressed={role !== null} className="shrink-0 active:scale-95">
              <span
                className={`relative block h-[78px] w-[78px] overflow-hidden rounded-2xl ring-offset-2 ring-offset-canvas transition ${
                  role === "After" ? "ring-[3px] ring-brand" : role === "Before" ? "ring-[3px] ring-[#8a8f95]" : "opacity-60"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={p.image_url} alt="" className="h-full w-full object-cover" />
                {role && (
                  <span className={`absolute inset-x-0 bottom-0 py-0.5 text-center text-[10px] font-bold uppercase tracking-wide text-white ${role === "After" ? "bg-brand" : "bg-[#14181a]/70"}`}>
                    {role}
                  </span>
                )}
              </span>
              <span className={`mt-1.5 block text-center text-xs font-semibold ${role ? "text-ink" : "text-muted"}`}>{fmtDate(p.captured_at)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
