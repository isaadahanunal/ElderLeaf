"use client";

import { useState } from "react";
import { TraceStep } from "@/lib/api";
import { IconAlert, IconCheck, IconMinus, IconSteps } from "./icons";
import { Card, Spinner } from "./ui";

function Dot({ status }: { status: TraceStep["status"] }) {
  const base = "grid h-7 w-7 shrink-0 place-items-center rounded-full";
  if (status === "running")
    return (
      <span className={`${base} bg-brand-soft text-brand`}>
        <Spinner className="h-3.5 w-3.5" />
      </span>
    );
  if (status === "done")
    return (
      <span className={`${base} bg-brand text-white`}>
        <IconCheck size={14} strokeWidth={2.6} />
      </span>
    );
  if (status === "failed")
    return (
      <span className={`${base} bg-warn-soft text-warn`}>
        <IconAlert size={14} />
      </span>
    );
  return (
    <span className={`${base} bg-well text-muted`}>
      <IconMinus size={14} />
    </span>
  );
}

/** The agent's steps as a vertical timeline. `live` shows every step; otherwise details are folded. */
export function AgentSteps({
  steps,
  live = false,
  scene,
  meta,
  actions,
}: {
  steps: TraceStep[];
  live?: boolean;
  scene?: string | null;
  meta?: string; // technical details: segmenter, SAM calls, cost, time
  actions?: React.ReactNode;
}) {
  const [open, setOpen] = useState(live);
  const done = steps.filter((s) => s.status === "done").length;
  return (
    <Card>
      <div className="flex items-center gap-3">
        <span className="grid h-[30px] w-[30px] place-items-center rounded-full bg-[#1111140f] text-ink">
          <IconSteps size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-ink-2">{live ? "Agent steps" : "How this was measured"}</div>
          <div className="text-xs text-muted">
            {live ? `${done} of ${steps.length} done` : `${steps.length} steps · numbers are computed in code, never by the language model`}
          </div>
          {!live && meta && <div className="mt-0.5 font-mono text-[11px] text-muted">{meta}</div>}
        </div>
        {actions}
        {!live && (
          <button onClick={() => setOpen(!open)} className="rounded-full bg-well px-3 py-1.5 text-xs font-semibold text-ink-2 hover:bg-[#ebe7de]">
            {open ? "Hide" : "Show"}
          </button>
        )}
      </div>

      {!open && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {steps.map((s) => (
            <span
              key={s.step}
              title={`${s.label}: ${s.result ?? ""}`}
              className={`rounded-full px-2.5 py-1 font-mono text-[11px] ${s.status === "done" ? "bg-brand-soft text-brand" : s.status === "failed" ? "bg-warn-soft text-warn" : "bg-well text-muted"}`}
            >
              {s.tool}
            </span>
          ))}
        </div>
      )}

      {open && (
        <>
          {scene && <p className="mt-4 rounded-2xl bg-well px-4 py-3 text-[13px] text-ink-2">Muse Spark saw: “{scene}”</p>}
          {steps.length === 0 && (
            <p className="mt-4 flex items-center gap-2 text-sm text-muted">
              <Spinner /> Starting…
            </p>
          )}
          <ol className="mt-4">
            {steps.map((s, i) => (
              <li key={s.step} className="relative flex gap-3 pb-4 last:pb-0">
                {i < steps.length - 1 && <span className="absolute left-[13px] top-8 h-[calc(100%-2rem)] w-0.5 bg-line" />}
                <Dot status={s.status} />
                <div className="min-w-0 pt-1">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="text-sm font-semibold">{s.label}</span>
                    <code className="font-mono text-[11px] text-muted">
                      {s.tool}
                      {s.input && s.tool === "run_sam" ? `("${s.input}")` : ""}
                    </code>
                  </div>
                  {s.result && <p className="mt-0.5 break-words text-[13px] text-muted">{s.result}</p>}
                  {s.image_url && (
                    <a href={s.image_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-[13px] font-semibold text-cover hover:underline">
                      See everything SAM returned →
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </Card>
  );
}
