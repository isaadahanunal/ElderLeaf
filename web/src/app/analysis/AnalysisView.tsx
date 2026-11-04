"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AnalysisOut, AnalysisResult, api, fmt, fmtDate, isNativeApp, MaskOut, PlotDetail } from "@/lib/api";
import { LayerToggles, MaskOverlay } from "@/components/MaskOverlay";
import { AssistantCard, assistantText, CoverCard, HealthCard, PlantsCard, SizeCard, SpotsCard, WaterCard, WeedsCard, weedFlag } from "@/components/MetricCards";
import { ReportCard } from "@/components/ReportCard";
import { RowVideo } from "@/components/RowVideo";
import { ShareResult } from "@/components/ShareResult";
import { AgentSteps } from "@/components/Trace";
import { IconDownload, IconSparkle, IconSprout } from "@/components/icons";
import { BackLink, Button, Card, Chip, CountUp, ErrorBox, InfoTip, LinkButton, Notice, SegmenterNotice, Skeleton, Spinner } from "@/components/ui";

export function AnalysisView() {
  const id = useSearchParams().get("id") ?? "";
  const [a, setA] = useState<AnalysisOut | null>(null);
  const [plot, setPlot] = useState<PlotDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState(0); // bumped by "Try again" to restart polling

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
  }, [id, runs]);

  const plotId = a?.plot_id;
  const doneNow = a?.status === "done";
  useEffect(() => {
    if (plotId) api.plot(plotId).then(setPlot, () => undefined);
  }, [plotId, doneNow]);

  async function rerun() {
    try {
      setError(null);
      setA(await api.rerun(id));
      setRuns((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const r = a?.result;
  const stats = r?.run_stats;
  const vstats = a?.video_result?.run_stats;
  const tech = [
    r?.segmenter ?? a?.video_result?.segmenter,
    stats ? `${stats.sam_calls} SAM calls` : vstats?.sam_calls !== undefined ? `${vstats.sam_calls} SAM calls` : null,
    stats ? `$${(stats.total_cost_usd ?? stats.sam_cost_usd).toFixed(3)}` : vstats?.sam_cost_usd !== undefined ? `$${vstats.sam_cost_usd.toFixed(3)}` : null,
    stats ? `${stats.wall_time_s.toFixed(0)} s` : vstats?.wall_time_s !== undefined ? `${vstats.wall_time_s.toFixed(0)} s` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const json =
    a?.status === "done" && r ? (
      isNativeApp() ? (
        // the Android WebView can't save a blob, so the system browser opens the JSON instead
        <LinkButton href={api.analysisJsonUrl(a.id)} external variant="secondary" size="sm">
          <IconDownload size={14} /> JSON
        </LinkButton>
      ) : (
        <Button variant="secondary" size="sm" onClick={() => downloadJson(r)}>
          <IconDownload size={14} /> JSON
        </Button>
      )
    ) : null;
  return (
    <>
      <BackLink href={a ? `/plot?id=${a.plot_id}` : "/"} label="Back to plot" />
      <div className="mb-6">
        <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[#8a6a35]">
          {a ? `${a.mode === "video" ? "Row count" : "Photo"} · ${fmtDate(a.captured_at)}` : "\u00a0"}
        </div>
        <h1 className="font-display mt-1 line-clamp-2 text-[32px] font-semibold leading-[1.08] sm:text-[36px]">
          {plot?.name ?? (a?.mode === "video" ? "Row count" : "Photo analysis")}
        </h1>
      </div>
      {error && <ErrorBox message={error} />}
      {!a && !error && <Skeleton className="h-96" />}
      {a && (a.status === "pending" || a.status === "running") && <Running a={a} />}
      {a?.status === "failed" && (
        <div className="space-y-4">
          <ErrorBox message={`The analysis stopped: ${a.error ?? "unknown error"}`} onRetry={rerun} />
          <AgentSteps steps={a.trace} live />
        </div>
      )}
      {a?.status === "done" && r && <PhotoResult a={a} r={r} plot={plot} tech={tech} json={json} />}
      {a?.status === "done" && a.video_result && a.video_url && <VideoDone a={a} tech={tech} />}
    </>
  );
}

function Running({ a }: { a: AnalysisOut }) {
  const current = [...a.trace].reverse().find((s) => s.status === "running") ?? a.trace.at(-1);
  const done = a.trace.filter((s) => s.status === "done").length;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
      <div className="relative min-h-64 overflow-hidden rounded-[26px] bg-forest shadow-[var(--shadow-lift)]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={a.image_url} alt="" className="w-full opacity-85 saturate-[0.85]" />
        <div className="scan-grid absolute inset-0" />
        <div className="scan-line" />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#0c1511]/85 via-[#0c1511]/40 to-transparent px-5 pb-5 pt-20">
          <div className="flex items-center gap-3.5 text-[#f6efe2]">
            <span className="breathe grid h-11 w-11 shrink-0 place-items-center rounded-full bg-gold text-forest shadow-lg">
              <IconSparkle size={20} />
            </span>
            <div className="min-w-0">
              <div className="font-display text-[20px] font-semibold leading-tight">{a.mode === "video" ? "Following every plant…" : "Measuring your plot…"}</div>
              <div className="flex items-center gap-2 truncate text-[13px] text-[#f6efe2]/75">
                <Spinner className="h-3 w-3 shrink-0" />
                {current ? `${current.label}${current.input && current.tool === "run_sam" ? ` · “${current.input}”` : ""}` : "Starting the agent"}
                {a.trace.length > 0 && <span className="text-[#f6efe2]/45">· {done} done</span>}
              </div>
            </div>
          </div>
        </div>
      </div>
      <AgentSteps steps={a.trace} live />
    </div>
  );
}

// ------------------------------------------------------------------ photo

function PhotoResult({ a, r, plot, tech, json }: { a: AnalysisOut; r: AnalysisResult; plot: PlotDetail | null; tech: string; json: React.ReactNode }) {
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
            <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2.5 rounded-2xl bg-[#0c1511]/70 py-2 pl-3.5 pr-4 text-white shadow-lg backdrop-blur">
              <span className="tabular text-[30px] font-bold leading-none">
                <CountUp value={m.plant_count.value ?? 0} />
              </span>
              <span className="text-[11px] font-semibold leading-tight text-white/80">
                plants
                <br />
                found
              </span>
            </div>
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
          <div className="mt-4">
            <ShareResult a={a} r={r} plot={plot} />
          </div>
        </div>
        {assistantText(r) ? <AssistantCard s={assistantText(r)!} consult={r.health.consult_agronomist} /> : <div />}
      </div>

      <SegmenterNotice name={r.segmenter} />
      {quality.level === "low" && (
        <Notice>
          <b>Photo quality is low</b> ({!quality.sharp ? "blurry" : quality.exposure.replace("_", " ")}), so the numbers may be off. Retake it in even light with a steady hand.
        </Notice>
      )}
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
            {(r.notes_since_previous ?? []).length > 0 && (
              <div className="mt-3 space-y-1.5">
                {(r.notes_since_previous ?? []).map((n, i) => (
                  <div key={i} className="rounded-xl bg-well px-3 py-2 text-[13px] text-ink-2">
                    <span className="font-semibold">{fmtDate(n.date)}</span> · {n.text}
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}
      </div>

      {r.report && <ReportCard report={r.report} analysisId={a.id} />}
      <AgentSteps steps={a.trace} scene={r.run_stats?.scene ?? null} meta={tech} actions={json} />
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

function VideoDone({ a, tech }: { a: AnalysisOut; tech: string }) {
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
      <AgentSteps steps={a.trace} meta={tech} />
    </div>
  );
}
