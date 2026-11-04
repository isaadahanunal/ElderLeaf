"use client";

import { ReactNode } from "react";
import { AnalysisResult, fmt, fmtDate, Irrigation, Summary } from "@/lib/api";
import { IconCheck, IconEye, IconFlag } from "./icons";
import { BigNumber, Card, CardHead, Chip, Delta, InfoTip, METRIC, MiniBars, Ring } from "./ui";

const WEED_FLAG_PCT = 25; // same rule as the API ("Many weeds")

function ShowMasks({ onClick, active }: { onClick?: () => void; active?: boolean }) {
  if (!onClick) return null;
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold transition ${active ? "bg-ink text-white" : "bg-well text-ink-2 hover:bg-[#ebe7de]"}`}
    >
      <IconEye size={13} /> {active ? "Hide" : "Masks"}
    </button>
  );
}

export function PlantsCard({
  value,
  delta,
  history,
  how,
  onShow,
  active,
  foot,
}: {
  value: number | null;
  delta?: number | null;
  history: (number | null)[];
  how?: string;
  onShow?: () => void;
  active?: boolean;
  foot?: string;
}) {
  return (
    <Card className={active ? "ring-2 ring-plants" : ""}>
      <CardHead m="plants" title="Plants" right={<>{how && <InfoTip>{how}</InfoTip>}</>} />
      <div className="flex items-end justify-between gap-3">
        <div>
          <BigNumber value={fmt(value, 0)} />
          <div className="mt-2 flex items-center gap-2">
            <Delta value={delta} />
            <span className="text-xs text-muted">{foot ?? "in the photo"}</span>
          </div>
        </div>
        <MiniBars values={history} color={METRIC.plants.hex} />
      </div>
      {onShow && (
        <div className="mt-3">
          <ShowMasks onClick={onShow} active={active} />
        </div>
      )}
    </Card>
  );
}

export function CoverCard({
  value,
  delta,
  band,
  day,
  how,
  onShow,
  active,
}: {
  value: number | null;
  delta?: number | null;
  band?: [number, number] | null;
  day?: number | null;
  how?: string;
  onShow?: () => void;
  active?: boolean;
}) {
  let status: ReactNode = null;
  if (band && value !== null) {
    if (value < band[0]) status = <Chip tone="warn">Below typical</Chip>;
    else if (value > band[1]) status = <Chip tone="good">Above typical</Chip>;
    else status = <Chip tone="good">Normal{day !== null && day !== undefined ? ` for day ${day}` : ""}</Chip>;
  }
  return (
    <Card className={active ? "ring-2 ring-cover" : ""}>
      <CardHead m="cover" title="Crop cover" right={how && <InfoTip>{how}</InfoTip>} />
      <div className="flex items-center gap-4">
        <Ring value={value} color={METRIC.cover.hex} band={band ?? undefined}>
          <span className="tabular text-xl font-bold">
            {fmt(value)}
            <span className="text-xs font-semibold text-muted">%</span>
          </span>
        </Ring>
        <div className="min-w-0 space-y-2">
          {status}
          {band && (
            <div className="flex items-center gap-1.5 text-xs text-muted">
              <span className="h-2 w-4 rounded-full" style={{ background: `${METRIC.cover.hex}38` }} />
              typical now {band[0]}–{band[1]}%
            </div>
          )}
          <Delta value={delta} unit=" pts" />
          {onShow && <ShowMasks onClick={onShow} active={active} />}
        </div>
      </div>
    </Card>
  );
}

export function WeedsCard({
  value,
  delta,
  flag,
  how,
  onShow,
  active,
}: {
  value: number | null;
  delta?: number | null;
  flag?: string | null;
  how?: string;
  onShow?: () => void;
  active?: boolean;
}) {
  const status = flag ? <Chip tone="warn">{flag}</Chip> : value !== null ? <Chip tone="good">Under control</Chip> : null;
  return (
    <Card className={active ? "ring-2 ring-weeds" : ""}>
      <CardHead m="weeds" title="Weeds" right={how && <InfoTip>{how}</InfoTip>} />
      <div className="flex items-center gap-4">
        <Ring value={value} color={METRIC.weeds.hex} tick={WEED_FLAG_PCT}>
          <span className="tabular text-xl font-bold">
            {fmt(value)}
            <span className="text-xs font-semibold text-muted">%</span>
          </span>
        </Ring>
        <div className="min-w-0 space-y-2">
          {status}
          <div className="text-xs text-muted">of the green area · flag at {WEED_FLAG_PCT}%</div>
          <Delta value={delta} unit=" pts" invert />
          {onShow && <ShowMasks onClick={onShow} active={active} />}
        </div>
      </div>
    </Card>
  );
}

export function SizeCard({
  value,
  unit,
  delta,
  history,
  scaleFound,
  how,
}: {
  value: number | null;
  unit: string;
  delta?: number | null;
  history: (number | null)[];
  scaleFound: boolean;
  how?: string;
}) {
  return (
    <Card>
      <CardHead m="size" title="Plant size" right={how && <InfoTip>{how}</InfoTip>} />
      <div className="flex items-end justify-between gap-3">
        <div>
          <BigNumber value={fmt(value, 0)} unit={unit === "cm2" ? "cm²" : " px"} />
          <div className="mt-2 flex items-center gap-2">
            <Delta value={delta} />
            <span className="text-xs text-muted">average per plant</span>
          </div>
        </div>
        <MiniBars values={history} color={METRIC.size.hex} />
      </div>
      <div className="mt-3">{scaleFound ? <Chip tone="good">A4 scale found</Chip> : <Chip>No A4 sheet: size in pixels</Chip>}</div>
    </Card>
  );
}

export function SpotsCard({ value, how, onShow, active }: { value: number | null; how?: string; onShow?: () => void; active?: boolean }) {
  return (
    <Card className={active ? "ring-2 ring-spots" : ""}>
      <CardHead m="spots" title="Leaf spots" right={how && <InfoTip>{how}</InfoTip>} />
      <div className="flex items-center gap-4">
        <Ring value={value} color={METRIC.spots.hex} tick={5}>
          <span className="tabular text-xl font-bold">
            {fmt(value)}
            <span className="text-xs font-semibold text-muted">%</span>
          </span>
        </Ring>
        <div className="space-y-2">
          <div className="text-xs text-muted">of the crop area · flag at 5%</div>
          {onShow && <ShowMasks onClick={onShow} active={active} />}
        </div>
      </div>
    </Card>
  );
}

export function WaterCard({ w }: { w: Irrigation | null }) {
  return (
    <Card>
      <CardHead m="water" title="Water today" right={w?.available && w.how ? <InfoTip>{`${w.how} FAO-56 method: a sparse plot uses less water than a full one, so the crop coefficient is scaled by the measured crop cover.`}</InfoTip> : undefined} />
      {w?.available ? (
        <>
          <BigNumber value={fmt(w.liters_per_m2)} unit=" L/m²" />
          <div className="mt-2 text-xs text-muted">
            {w.plot_total_liters !== null && w.plot_total_liters !== undefined ? (
              <>
                about <b className="text-ink">{w.plot_total_liters} L</b> for the whole plot
              </>
            ) : (
              "add the plot area for a total"
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {w.et0_mm !== undefined && <Chip>ET0 {w.et0_mm} mm</Chip>}
            {w.rain_mm !== undefined && w.rain_mm >= 1 && <Chip tone="brand">Rain {w.rain_mm} mm</Chip>}
          </div>
        </>
      ) : (
        <p className="text-sm text-muted">{w?.reason ?? "Loading the weather…"}</p>
      )}
    </Card>
  );
}

export function HealthCard({ r, onShow }: { r: AnalysisResult; onShow?: (ids: string[]) => void }) {
  const h = r.health;
  return (
    <Card>
      <CardHead
        m="health"
        title="Plant health"
        right={<InfoTip label="About this check">Possible signs only, never a diagnosis: the same sign can have several causes. The consult flag is set by rules in code (photo quality, spot area, detection confidence below 0.6).</InfoTip>}
      />
      {h.consult_agronomist ? (
        <Chip tone="warn">
          <IconFlag size={12} /> Ask an agronomist
        </Chip>
      ) : (
        <Chip tone="good">
          <IconCheck size={12} /> No flags
        </Chip>
      )}
      <ul className="mt-3 space-y-1.5 text-[13px] text-ink-2">
        {h.signs.map((s, i) => (
          <li key={i} className="flex items-center justify-between gap-2">
            <span>{s.description}</span>
            {onShow && s.evidence_mask_ids.length > 0 && <ShowMasks onClick={() => onShow(s.evidence_mask_ids)} />}
          </li>
        ))}
        {h.consult_reasons.map((c) => (
          <li key={c} className="flex gap-2">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-health" />
            {c}
          </li>
        ))}
        {!h.assessed && !h.consult_reasons.length && <li className="text-muted">Leaf-spot check is off for this photo.</li>}
        {h.detection_confidence !== null && <li className="text-xs text-muted">Detection confidence {h.detection_confidence.toFixed(2)}</li>}
      </ul>
    </Card>
  );
}

export function AssistantCard({ s, title = "ElderLeaf assistant", consult, compact }: { s: Summary; title?: string; consult?: boolean; compact?: boolean }) {
  return (
    <Card className={compact ? "" : "h-full"}>
      <div className="flex items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="" width={42} height={42} className="h-[42px] w-[42px] shrink-0 rounded-full ring-2 ring-gold/60" />
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold">{title}</div>
          <div className="text-xs text-muted">{s.source === "agent" ? "Muse Spark · every number checked" : "Written from your measurements"}</div>
        </div>
        {(s.validator_issues.length > 0 || s.source === "agent") && (
          <InfoTip label="Validator">
            {s.validator_issues.length > 0
              ? `Before you saw this, the validator rejected: ${s.validator_issues.join("; ")}.`
              : "Every number in this text was checked against your measurements. Chemical names, doses and disease names are not allowed."}
          </InfoTip>
        )}
      </div>
      <div className="mt-4 rounded-2xl rounded-tl-md bg-well px-4 py-3 text-[15px] leading-relaxed text-ink">{s.text}</div>
      {s.next_step && (
        <div className="mt-3 flex items-start gap-3 rounded-2xl bg-brand-soft px-4 py-3 text-sm text-brand">
          <IconCheck size={16} className="mt-0.5 shrink-0" />
          <span>
            <b>This week · </b>
            {s.next_step}
          </span>
        </div>
      )}
      {consult && (
        <div className="mt-3 flex items-center gap-2 text-[13px] font-semibold text-health">
          <IconFlag size={14} /> Worth showing to an agronomist
        </div>
      )}
    </Card>
  );
}

export function weedFlag(r: AnalysisResult | null | undefined): string | null {
  const item = r?.context.find((c) => c.metric === "weed_share_pct" && c.status === "attention");
  return item?.badge ?? null;
}

export function dateLabel(iso: string) {
  return fmtDate(iso);
}
