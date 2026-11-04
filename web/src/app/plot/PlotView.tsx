"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AnalysisOut, AnalysisSummary, api, CompareOut, fmt, fmtDate, Irrigation, Note, PlotDetail, today } from "@/lib/api";
import { MaskOverlay } from "@/components/MaskOverlay";
import { AssistantCard, CoverCard, PlantsCard, WaterCard, WeedsCard, weedFlag } from "@/components/MetricCards";
import { TrendCharts } from "@/components/TrendCharts";
import { IconCamera, IconChevronRight, IconDownload, IconDroplet, IconNote, IconVideo } from "@/components/icons";
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

  const photos = plot.analyses.filter((a) => a.mode === "photo" && a.status === "done");
  return (
    <>
      <BackLink href="/" label="All plots" />
      <PageHead
        title={plot.name}
        chips={
          <>
            <Chip tone="brand">{plot.crop_label}</Chip>
            {plot.days_after_planting !== null && <Chip>Day {plot.days_after_planting}</Chip>}
            {plot.area_m2 && <Chip>{plot.area_m2} m²</Chip>}
            {plot.planted_on && <Chip>Planted {fmtDate(plot.planted_on)}</Chip>}
            {plot.is_demo && <Chip tone="dark">Demo · read-only</Chip>}
          </>
        }
        actions={
          !plot.is_demo && (
            <>
              <LinkButton href={`/analyze?plot=${plot.id}&mode=video`} variant="white">
                <IconVideo size={16} /> Row video
              </LinkButton>
              <LinkButton href={`/analyze?plot=${plot.id}`}>
                <IconCamera size={16} /> Analyze photo
              </LinkButton>
            </>
          )
        }
      />
      <div className="mb-6">
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
  const photos = plot.analyses.filter((a) => a.mode === "photo" && a.status === "done");
  const latestPhoto = photos.at(-1);
  const [latest, setLatest] = useState<AnalysisOut | null>(null);
  const [water, setWater] = useState<Irrigation | null>(null);

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
          {r?.summary ? <AssistantCard s={r.summary} consult={r.health.consult_agronomist} /> : <Skeleton className="h-64" />}
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
      <div className="order-1 space-y-4 lg:order-2">
        {!plot.is_demo && <NoteForm plotId={plot.id} onSaved={onChange} />}
        <LinkButton href={api.csvUrl(plot.id)} external variant="white" className="w-full">
          <IconDownload size={16} /> Export CSV
        </LinkButton>
      </div>
    </div>
  );
}

function EntryCard({ a }: { a: AnalysisSummary }) {
  const running = a.status === "pending" || a.status === "running";
  return (
    <Link href={`/analysis?id=${a.id}`} className="flex gap-4 rounded-2xl bg-card p-3 pr-4 shadow-[var(--shadow-card)] transition hover:shadow-md">
      <div className="relative h-20 w-24 shrink-0 overflow-hidden rounded-xl bg-[#e6e7eb]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={a.image_url} alt="" className="h-full w-full object-cover" />
        <span className="absolute bottom-1 left-1 grid h-6 w-6 place-items-center rounded-full bg-white/90 text-ink">{a.mode === "video" ? <IconVideo size={13} /> : <IconCamera size={13} />}</span>
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
        {a.status === "done" &&
          (a.mode === "video" ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Stat m="plants" text={`${a.row_plant_count ?? "–"} plants in the row`} />
            </div>
          ) : (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Stat m="plants" text={`${fmt(a.plant_count, 0)} plants`} />
              <Stat m="cover" text={`${fmt(a.canopy_cover_pct)}% cover`} />
              <Stat m="weeds" text={`${fmt(a.weed_share_pct)}% weeds`} />
            </div>
          ))}
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
    <div className="flex items-center gap-4 rounded-2xl border border-dashed border-[#d8d9de] px-4 py-3">
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

function NoteForm({ plotId, onSaved }: { plotId: string; onSaved: () => void }) {
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
  return (
    <Card>
      <div className="mb-3 text-[15px] font-bold">Add a note</div>
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {NOTE_KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              onClick={() => setKind(k.id)}
              className={`h-8 rounded-full px-3 text-[13px] font-semibold transition ${kind === k.id ? "bg-ink text-white" : "bg-well text-ink-2 hover:bg-[#e9eaee]"}`}
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

  const older = cmp ? full[cmp.a.id] : undefined;
  const newer = cmp ? full[cmp.b.id] : undefined;
  const visible = useMemo(() => new Set(["crop", "weed", "lesion"]), []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <DatePick value={aId} onChange={setAId} photos={photos} />
        <IconChevronRight size={16} className="text-muted" />
        <DatePick value={bId} onChange={setBId} photos={photos} />
        {cmp && <Chip>{cmp.days_between} days apart</Chip>}
      </div>
      {aId === bId && <p className="text-sm text-muted">Pick two different dates.</p>}
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
              <span className="absolute left-3 top-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold">{fmtDate(cmp.a.captured_at)}</span>
              <span className="absolute right-3 top-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold">{fmtDate(cmp.b.captured_at)}</span>
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
                  .filter((r) => r.a !== null || r.b !== null)
                  .map((r) => {
                    const m = COMPARE_META[r.metric] ?? "plants";
                    const u = r.unit === "cm2" ? " cm²" : r.unit === "%" ? "%" : r.unit === "px" ? " px" : "";
                    const max = Math.max(r.a ?? 0, r.b ?? 0, 1e-9);
                    return (
                      <div key={r.metric} className="py-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-2 text-sm font-semibold text-ink-2">
                            <span className="h-2.5 w-2.5 rounded-full" style={{ background: METRIC[m].hex }} />
                            {r.label}
                          </span>
                          <span className="flex items-center gap-2">
                            <span className="tabular text-sm font-bold">
                              {r.b === null ? "–" : `${fmt(r.b)}${u}`}
                            </span>
                            <Delta value={r.delta} unit={u === "%" ? " pts" : ""} invert={r.metric === "weed_share_pct" || r.metric === "lesion_share_pct"} />
                          </span>
                        </div>
                        <div className="mt-2 space-y-1">
                          <div className="h-1.5 rounded-full bg-[#eceef2]">
                            <div className="h-1.5 rounded-full bg-[#c9ccd3]" style={{ width: `${((r.a ?? 0) / max) * 100}%` }} />
                          </div>
                          <div className="h-1.5 rounded-full bg-[#eceef2]">
                            <div className="h-1.5 rounded-full" style={{ width: `${((r.b ?? 0) / max) * 100}%`, background: METRIC[m].hex }} />
                          </div>
                        </div>
                      </div>
                    );
                  })}
              </div>
              <div className="mt-2 flex gap-4 text-xs text-muted">
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-4 rounded-full bg-[#c9ccd3]" /> {fmtDate(cmp.a.captured_at)}
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-4 rounded-full bg-ink" /> {fmtDate(cmp.b.captured_at)}
                </span>
              </div>
            </Card>
          </div>
        )}
      </div>
      {cmp && (
        <div className="grid gap-4 lg:grid-cols-2">
          <AssistantCard s={cmp.summary} title="Change summary" compact />
          {cmp.notes_between.length > 0 && (
            <Card>
              <div className="mb-3 text-[15px] font-bold">Your notes in between</div>
              <div className="space-y-2">
                {cmp.notes_between.map((n) => (
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

function DatePick({ value, onChange, photos }: { value: string; onChange: (v: string) => void; photos: AnalysisSummary[] }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="h-10 rounded-full bg-card px-4 text-sm font-semibold shadow-[var(--shadow-card)] outline-none">
      {photos.map((p) => (
        <option key={p.id} value={p.id}>
          {fmtDate(p.captured_at)}
        </option>
      ))}
    </select>
  );
}
