"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { VideoResult } from "@/lib/api";

const PALETTE = ["#1f9d55", "#0891b2", "#2563eb", "#7c4dcc", "#c2185b", "#e8590c"];

/** Plays the row video with each plant's id drawn on it and a counter that climbs as the walk goes on. */
export function RowVideo({ src, result }: { src: string; result: VideoResult }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [count, setCount] = useState(0);
  const counted = useMemo(() => new Set(result.tracks.filter((t) => t.counted).map((t) => t.track_id)), [result]);
  const firstSeen = useMemo(() => {
    const m = new Map<number, number>();
    for (const t of result.tracks) if (t.counted) m.set(t.track_id, t.first_t);
    return m;
  }, [result]);
  // number counted plants 1..N in the order they appear
  const ordinal = useMemo(() => {
    const ids = [...firstSeen.entries()].sort((a, b) => a[1] - b[1] || a[0] - b[0]).map(([id]) => id);
    return new Map(ids.map((id, i) => [id, i + 1]));
  }, [firstSeen]);

  useEffect(() => {
    let raf = 0;
    const draw = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      if (video && canvas && ctx) {
        const t = video.currentTime;
        // the sampled frame closest to now
        let frame = result.frames[0];
        for (const f of result.frames) {
          if (f.t <= t + 0.05) frame = f;
          else break;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const lw = Math.max(2, canvas.width / 320);
        ctx.font = `700 ${Math.round(canvas.width / 26)}px ui-sans-serif, system-ui, sans-serif`;
        for (const b of frame?.boxes ?? []) {
          if (!counted.has(b.track_id)) continue;
          const [x0, y0, x1, y1] = b.box;
          const n = ordinal.get(b.track_id) ?? b.track_id;
          const color = PALETTE[n % PALETTE.length];
          ctx.lineWidth = lw;
          ctx.strokeStyle = color;
          ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
          const label = `#${n}`;
          const w = ctx.measureText(label).width + 12;
          const h = canvas.width / 20;
          ctx.fillStyle = color;
          ctx.fillRect(x0, Math.max(0, y0 - h), w, h);
          ctx.fillStyle = "#fff";
          ctx.fillText(label, x0 + 6, Math.max(h * 0.78, y0 - h * 0.22));
        }
        let c = 0;
        for (const ft of firstSeen.values()) if (ft <= t + 0.05) c++;
        setCount(video.ended ? counted.size : c);
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [result, counted, firstSeen, ordinal]);

  return (
    <div className="relative w-full overflow-hidden rounded-2xl bg-black" style={{ aspectRatio: `${result.width} / ${result.height}` }}>
      <video ref={videoRef} src={src} className="absolute inset-0 h-full w-full" playsInline muted controls loop preload="auto" />
      <canvas ref={canvasRef} width={result.width} height={result.height} className="pointer-events-none absolute inset-0 h-full w-full" />
      <div className="pointer-events-none absolute right-3 top-3 flex items-center gap-2.5 rounded-2xl bg-white/95 py-2 pl-2 pr-3.5 shadow-lg">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-[#1f9d551a] text-[#1f9d55]">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 21v-9M12 12c0-4 3-7 8-7 0 4-3 7-8 7zM12 14c0-3-2.5-5.5-7-5.5 0 3 2.5 5.5 7 5.5z" />
          </svg>
        </span>
        <span>
          <span className="tabular block text-2xl font-bold leading-none text-ink">{count}</span>
          <span className="block text-[11px] font-medium text-muted">of {counted.size} plants</span>
        </span>
      </div>
    </div>
  );
}
