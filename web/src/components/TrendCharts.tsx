"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AnalysisSummary, fmt, fmtDate } from "@/lib/api";
import { Card, CardHead, METRIC, MetricKey } from "./ui";

// One series per card (small multiples): the card title names it, so no legend. Each metric keeps
// its own color everywhere in the app (validated on white with the dataviz palette checker).
const GRID = "#eef0f3";
const MUTED = "#85858f";

type Key = "plant_count" | "canopy_cover_pct" | "weed_share_pct" | "lesion_share_pct" | "row_plant_count";

const CHARTS: { key: Key; m: MetricKey; title: string; unit: string }[] = [
  { key: "plant_count", m: "plants", title: "Plants in the photo", unit: "" },
  { key: "canopy_cover_pct", m: "cover", title: "Crop cover", unit: "%" },
  { key: "weed_share_pct", m: "weeds", title: "Weed share", unit: "%" },
  { key: "lesion_share_pct", m: "spots", title: "Leaf spots", unit: "%" },
  { key: "row_plant_count", m: "plants", title: "Plants in the row (video)", unit: "" },
];

export function TrendCharts({ analyses }: { analyses: AnalysisSummary[] }) {
  const [table, setTable] = useState(false);
  const done = analyses.filter((a) => a.status === "done");
  const charts = CHARTS.map((c) => ({
    ...c,
    data: done
      .filter((a) => a[c.key] !== null && a[c.key] !== undefined)
      .map((a) => ({ date: a.captured_at, label: fmtDate(a.captured_at), value: a[c.key] as number })),
  })).filter((c) => c.data.length > 0);
  if (!charts.length) return null;

  return (
    <div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {charts.map((c) => (
          <Card key={c.key}>
            <CardHead
              m={c.m}
              title={c.title}
              right={
                <span className="tabular text-[15px] font-bold">
                  {fmt(c.data[c.data.length - 1].value)}
                  {c.unit}
                </span>
              }
            />
            {c.data.length < 2 ? (
              <p className="py-8 text-center text-[13px] text-muted">One measurement so far. The trend appears after the next one.</p>
            ) : (
              <div className="h-36" role="img" aria-label={`${c.title}: ${c.data.map((d) => `${d.label} ${fmt(d.value)}${c.unit}`).join(", ")}`}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={c.data} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke={GRID} vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: MUTED }} tickLine={false} axisLine={false} />
                    <YAxis
                      tick={{ fontSize: 11, fill: MUTED }}
                      tickLine={false}
                      axisLine={false}
                      width={36}
                      tickCount={3}
                      allowDecimals={false}
                      tickFormatter={(v: number) => `${Math.round(v)}${c.unit}`}
                    />
                    <Tooltip
                      cursor={{ fill: "rgba(0,0,0,0.04)" }}
                      content={({ active, payload }) =>
                        active && payload?.length ? (
                          <div className="rounded-xl bg-ink px-3 py-2 text-xs text-white shadow-lg">
                            <div className="text-white/60">{fmtDate(payload[0].payload.date)}</div>
                            <div className="text-sm font-bold">
                              {fmt(payload[0].value as number)}
                              {c.unit}
                            </div>
                          </div>
                        ) : null
                      }
                    />
                    <Bar dataKey="value" fill={METRIC[c.m].hex} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        ))}
      </div>
      <button onClick={() => setTable(!table)} className="mt-3 text-[13px] font-semibold text-muted hover:text-ink">
        {table ? "Hide table" : "View as table"}
      </button>
      {table && (
        <Card className="mt-3 overflow-x-auto p-0">
          <table className="tabular w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-5 py-3 font-semibold">Date</th>
                {charts.map((c) => (
                  <th key={c.key} className="px-5 py-3 font-semibold">
                    {c.title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {done.map((a) => (
                <tr key={a.id} className="border-t border-line">
                  <td className="px-5 py-2.5 text-muted">{fmtDate(a.captured_at)}</td>
                  {charts.map((c) => (
                    <td key={c.key} className="px-5 py-2.5">
                      {a[c.key] === null || a[c.key] === undefined ? "–" : `${fmt(a[c.key] as number)}${c.unit}`}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
