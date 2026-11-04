"use client";

import { ReactNode, useState } from "react";
import { apiUrl, Report } from "@/lib/api";
import { IconChevronRight, IconNote } from "./icons";
import { Card } from "./ui";

// The report agent writes a short Markdown report (headings, a table, bullets, bold). This draws that subset
// as React elements, so no HTML from the server is ever injected into the page.
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <b key={i}>{part.slice(2, -2)}</b>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="rounded bg-well px-1 font-mono text-[12px]">{part.slice(1, -1)}</code>;
    return part;
  });
}

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `l${i}`;
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const row = cells(lines[i]);
        if (!row.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(row);
        i++;
      }
      const [head, ...body] = rows;
      out.push(
        <div key={key} className="my-3 overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-well text-ink-2">
              <tr>{head.map((c, j) => <th key={j} className="px-3 py-2 font-semibold">{inline(c)}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-line">
              {body.map((r, k) => (
                <tr key={k}>{r.map((c, j) => <td key={j} className="px-3 py-2 align-top text-ink-2">{inline(c)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ""));
        i++;
      }
      out.push(
        <ul key={key} className="my-2 list-disc space-y-1 pl-5 text-[14px] text-ink-2">
          {items.map((t, j) => <li key={j}>{inline(t)}</li>)}
        </ul>,
      );
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      out.push(
        <div key={key} className={level === 1 ? "font-display mt-1 text-[20px] font-semibold" : "mt-4 text-[15px] font-semibold text-ink"}>
          {inline(h[2])}
        </div>,
      );
      i++;
      continue;
    }
    out.push(
      <p key={key} className="my-2 text-[14px] leading-relaxed text-ink-2">
        {inline(line)}
      </p>,
    );
    i++;
  }
  return <div>{out}</div>;
}

/** The report agent's full report, folded by default. */
export function ReportCard({ report, analysisId }: { report: Report; analysisId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 text-left" aria-expanded={open}>
        <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-brand-soft text-brand">
          <IconNote size={16} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-semibold text-ink-2">Full report</span>
          <span className="block text-xs text-muted">
            {report.written_by === "agent" ? "Written by the report agent, every number checked by the validator" : "Written from your measurements"}
          </span>
        </span>
        <IconChevronRight size={16} className={`shrink-0 text-muted transition ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="fade-in mt-3 border-t border-line pt-2">
          <Markdown text={report.markdown} />
          <a href={`${apiUrl()}/analyses/${analysisId}/report.md`} target="_blank" rel="noreferrer" className="mt-3 inline-block text-[13px] font-semibold text-brand hover:underline">
            Open as Markdown
          </a>
        </div>
      )}
    </Card>
  );
}
