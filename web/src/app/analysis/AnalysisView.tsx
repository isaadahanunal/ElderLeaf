"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AnalysisOut, AnalysisResult, api, fmt, fmtDate, MaskOut, PlotDetail } from "@/lib/api";
import { LayerToggles, MaskOverlay } from "@/components/MaskOverlay";
import { AssistantCard, CoverCard, HealthCard, PlantsCard, SizeCard, SpotsCard, WaterCard, WeedsCard, weedFlag } from "@/components/MetricCards";
import { RowVideo } from "@/components/RowVideo";
import { AgentSteps } from "@/components/Trace";
import { IconDownload, IconSprout } from "@/components/icons";
import { BackLink, Button, Card, Chip, ErrorBox, InfoTip, LinkButton, Notice, PageHead, SegmenterNotice, Skeleton, Spinner } from "@/components/ui";

export function AnalysisView() {
  const id = useSearchParams().get("id") ?? "";
  const [a, setA] = useState<AnalysisOut | null>(null);
  const [plot, setPlot] = useState<PlotDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await api.analysis(id);
        if (stop) return;
        setA(next);
        if (next.status === "pending" || next.status === "running") timer = setTimeout(tick, 1000);
      } catch (e) {
        if (!stop) setError((e as Error).message);
      }
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [id]);

  const plotId = a?.plot_id;
  const doneNow = a?.status === "done";
  useEffect(() => {
    if (plotId) api.plot(plotId).then(setPlot, () => undefined);
  }, [plotId, doneNow]);

  async function rerun() {
    try {
      await api.rerun(id);
      window.location.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const r = a?.result;
  const stats = r?.run_stats;
  return (
    <>
      <BackLink href={a ? `/plot?id=${a.plot_id}` : "/"} label={plot?.name ?? "Back"} />
      <PageHead
        title={a?.mode === "video" ? "Row count" : "Photo analysis"}
        chips={
          a && (
            <>
              <Chip tone="brand">{fmtDate(a.captured_at)}</Chip>
              {(r?.segmenter ?? a.video_result?.segmenter) && <Chip>{r?.segmenter ?? a.video_result?.segmenter}</Chip>}
              {stats && <Chip>{stats.sam_calls} SAM calls</Chip>}
              {stats && <Chip>{stats.total_cost_usd !== null ? `$${stats.total_cost_usd.toFixed(3)}` : `$${stats.sam_cost_usd.toFixed(3)}`}</Chip>}
              {stats && <Chip>{stats.wall_time_s.toFixed(0)} s</Chip>}
            </>
          )
        }
        actions={
          a?.status === "done" && (
            <>
              {r && (
                <Button variant="white" onClick={() => downloadJson(r)}>
                  <IconDownload size={16} /> JSON
                </Button>
              )}
              <LinkButton href={`/plot?id=${a.plot_id}`} variant="white">
                Open plot
              </LinkButton>
            </>
          )
        }
      />
      {error && <ErrorBox message={error} />}
      {!a && !error && <Skeleton className="h-96" />}
      {a && (a.status === "pending" || a.status === "running") && <Running a={a} />}
      {a?.status === "failed" && (
        <div className="space-y-4">
          <ErrorBox message={`The analysis stopped: ${a.error ?? "unknown error"}`} onRetry={rerun} />
          <AgentSteps steps={a.trace} live />
        </div>
      )}
      {a?.status === "done" && r && <PhotoResult a={a} r={r} plot={plot} />}
      {a?.status === "done" && a.video_result && a.video_url && <VideoDone a={a} />}
    </>
  );
}

function Running({ a }: { a: AnalysisOut }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
      <div className="relative overflow-hidden rounded-2xl bg-[#e6e7eb]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={a.image_url} alt="" className="w-full opacity-70" />
        <div className="absolute inset-0 grid place-items-center">
          <span className="flex items-center gap-2.5 rounded-full bg-white px-5 py-3 text-sm font-semibold shadow-xl">
            <Spinner className="text-brand" /> {a.mode === "video" ? "Following every plant…" : "Measuring your plot…"}
          </span>
        </div>
      </div>
      <AgentSteps steps={a.trace} live />
    </div>
  );
}

// ------------------------------------------------------------------ photo

function PhotoResult({ a, r, plot }: { a: AnalysisOut; r: AnalysisResult; plot: PlotDetail | null }) {
  const counts = useMemo(() => {
    const c: Record<string, number> = { crop: 0, weed: 0 };
    for (const m of r.masks) c[m.class] = (c[m.class] ?? 0) + 1;
    return c;
  }, [r]);
  const [visible, setVisible] = useState(new Set(["crop", "weed", "lesion", "scale"]));
  const [highlight, setHighlight] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<MaskOut | null>(null);
  const [active, setActive] = useState<string | null>(null);

  const toggle = (cls: string) =>
    setVisible((v) => {
      const n = new Set(v);
      if (n.has(cls)) n.delete(cls);
      else n.add(cls);
      return n;
    });

  function focus(key: string, ids: string[]) {
    if (active === key) {
      setActive(null);
      setHighlight(new Set());
      return;
    }
    setActive(key);
    setSelected(null);
    setHighlight(new Set(ids));
    document.getElementById("overlay")?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const m = r.metrics;
  const d = r.comparison?.deltas ?? {};
  // history up to this analysis, for the little bar charts
  const upTo = (plot?.analyses ?? []).filter((x) => x.mode === "photo" && x.status === "done" && x.captured_at <= a.captured_at);
  const quality = r.image_quality;
  return (
    <div className="space-y-6">
      <SegmenterNotice name={r.segmenter} />
      {quality.level === "low" && (
        <Notice>
          <b>Photo quality is low</b> ({!quality.sharp ? "blurry" : quality.exposure.replace("_", " ")}), so the numbers may be off. Retake it in even light with a steady hand.
        </Notice>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <div id="overlay" className="min-w-0">
          <div className="relative">
            <MaskOverlay
              imageUrl={a.image_url}
              width={r.image.width}
              height={r.image.height}
              masks={r.masks}
              visible={visible}
              highlight={highlight}
              onSelect={(mask) => {
                setSelected(mask);
                setActive(null);
                setHighlight(mask ? new Set([mask.id]) : new Set());
              }}
            />
            {selected && (
              <div className="fade-in absolute bottom-3 left-3 right-3 flex items-center gap-3 rounded-2xl bg-white/95 px-4 py-2.5 text-[13px] shadow-lg backdrop-blur sm:right-auto">
                <span className="font-mono font-semibold">{selected.id}</span>
                <span className="capitalize text-muted">{selected.class}</span>
                {selected.score !== null && <span>conf. {selected.score.toFixed(2)}</span>}
                <span className="font-semibold">{r.scale.px_per_cm2 ? `${fmt(selected.area_px / r.scale.px_per_cm2)} cm²` : `${selected.area_px} px`}</span>
              </div>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <LayerToggles counts={counts} visible={visible} onToggle={toggle} />
            <span className="text-xs text-muted">Tap a plant to inspect its mask</span>
          </div>
        </div>
        {r.summary ? <AssistantCard s={r.summary} consult={r.health.consult_agronomist} /> : <div />}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <PlantsCard
          value={m.plant_count.value}
          delta={d.plant_count}
          history={upTo.map((x) => x.plant_count)}
          how={m.plant_count.how}
          onShow={() => focus("plants", m.plant_count.mask_ids)}
          active={active === "plants"}
        />
        <CoverCard
          value={m.canopy_cover_pct.value}
          delta={d.canopy_cover_pct}
          band={r.crop_info?.cover_typical_pct ?? null}
          day={r.days_after_planting}
          how={m.canopy_cover_pct.how}
          onShow={() => focus("cover", m.canopy_cover_pct.mask_ids)}
          active={active === "cover"}
        />
        <WeedsCard
          value={m.weed_share_pct.value}
          delta={d.weed_share_pct}
          flag={weedFlag(r)}
          how={m.weed_share_pct.how}
          onShow={m.weed_share_pct.mask_ids.length ? () => focus("weeds", m.weed_share_pct.mask_ids) : undefined}
          active={active === "weeds"}
        />
        {m.lesion_share_pct ? (
          <SpotsCard
            value={m.lesion_share_pct.value}
            how={m.lesion_share_pct.how}
            onShow={m.lesion_share_pct.mask_ids.length ? () => focus("spots", m.lesion_share_pct!.mask_ids) : undefined}
            active={active === "spots"}
          />
        ) : (
          <SizeCard
            value={m.mean_plant_area.value}
            unit={m.mean_plant_area.unit}
            delta={d.mean_plant_area}
            history={upTo.map((x) => (x.mean_plant_area_unit === m.mean_plant_area.unit ? x.mean_plant_area : null))}
            scaleFound={r.scale.found}
            how={`${m.mean_plant_area.how} ${r.scale.note}`}
          />
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <HealthCard r={r} onShow={(ids) => focus("health", ids)} />
        <WaterCard w={r.irrigation} />
        {r.comparison && (
          <Card>
            <div className="mb-3 flex items-center gap-2.5">
              <span className="grid h-[30px] w-[30px] place-items-center rounded-full bg-brand-soft text-brand">
                <IconSprout size={16} />
              </span>
              <span className="flex-1 text-[15px] font-semibold text-ink-2">Since {fmtDate(r.comparison.previous_captured_at)}</span>
              <InfoTip label="Growth rate">
                {Object.entries(r.comparison.growth_rate)
                  .map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`)
                  .join(" · ") || "Not enough days between photos."}
              </InfoTip>
            </div>
            <p className="text-[15px] font-semibold">{r.comparison.summary}</p>
            {r.notes_since_previous.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {r.notes_since_previous.map((n, i) => (
                  <div key={i} className="rounded-xl bg-well px-3 py-2 text-[13px] text-ink-2">
                    <span className="font-semibold">{fmtDate(n.date)}</span> · {n.text}
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}
      </div>

      <AgentSteps steps={a.trace} scene={r.run_stats?.scene ?? null} />
    </div>
  );
}

function downloadJson(r: AnalysisResult) {
  const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `elderleaf-${r.analysis_id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ------------------------------------------------------------------ video

function VideoDone({ a }: { a: AnalysisOut }) {
  const v = a.video_result!;
  return (
    <div className="space-y-6">
      <SegmenterNotice name={v.segmenter} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <RowVideo src={a.video_url!} result={v} />
        <div className="space-y-4">
          <Card>
            <div className="flex items-center gap-4">
              <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-[#1f9d551a] text-plants">
                <IconSprout size={30} />
              </span>
              <div>
                <div className="tabular text-5xl font-bold leading-none tracking-tight">{v.row_plant_count}</div>
                <div className="mt-1 text-sm text-muted">plants in this row, each counted once</div>
              </div>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-2 text-center">
              {[
                [`${v.duration_s.toFixed(0)} s`, "video"],
                [String(v.frames.length), "frames checked"],
                [String(v.max_per_frame), "max in view"],
              ].map(([val, label]) => (
                <div key={label} className="rounded-2xl bg-well px-2 py-3">
                  <div className="tabular text-lg font-bold">{val}</div>
                  <div className="text-xs text-muted">{label}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between">
              <Chip>SAM phrase “{v.prompt}”</Chip>
              <InfoTip label="How it's counted">{v.how}</InfoTip>
            </div>
          </Card>
          {v.context
            .filter((c) => c.status === "attention")
            .map((c, i) => (
              <Notice key={i}>{c.text}</Notice>
            ))}
        </div>
      </div>
      <AgentSteps steps={a.trace} />
    </div>
  );
}
