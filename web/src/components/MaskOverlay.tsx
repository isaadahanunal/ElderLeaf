"use client";

import { useEffect, useMemo, useRef } from "react";
import { CLASS_COLORS, MaskOut } from "@/lib/api";

const MAX_CANVAS = 1400;
const REVEAL_MS = 1400;

function hexToRgba(hex: string, alpha: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** Photo with SAM masks drawn on a canvas. Tap a mask to select it. */
export function MaskOverlay({
  imageUrl,
  width,
  height,
  masks,
  visible,
  highlight,
  onSelect,
  rounded = true,
  fill = false,
  reveal = true,
}: {
  imageUrl: string;
  width: number;
  height: number;
  masks: MaskOut[];
  visible: Set<string>;
  highlight?: Set<string>;
  onSelect?: (mask: MaskOut | null) => void;
  rounded?: boolean;
  fill?: boolean; // fill the parent box instead of keeping the photo's aspect ratio
  reveal?: boolean; // animate the masks in when they first appear
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const scale = Math.min(1, MAX_CANVAS / Math.max(width, height));

  const paths = useMemo(() => {
    const out = new Map<string, Path2D>();
    for (const m of masks) {
      const p = new Path2D();
      for (const poly of m.polygons) {
        poly.forEach(([x, y], i) => (i === 0 ? p.moveTo(x * scale, y * scale) : p.lineTo(x * scale, y * scale)));
        p.closePath();
      }
      out.set(m.id, p);
    }
    return out;
  }, [masks, scale]);

  // masks appear one by one from the top of the photo down, like the scan that found them
  const revealStart = useRef<{ masks: MaskOut[]; t: number } | null>(null);
  const order = useMemo(() => {
    const sorted = [...masks].sort((a, b) => a.box[1] + a.box[3] - (b.box[1] + b.box[3]) || a.box[0] - b.box[0]);
    return new Map(sorted.map((m, i) => [m.id, sorted.length > 1 ? i / (sorted.length - 1) : 0]));
  }, [masks]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const still = !reveal || (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
    if (revealStart.current?.masks !== masks) revealStart.current = { masks, t: performance.now() };
    const anyHighlight = highlight && highlight.size > 0;
    const lw = Math.max(1.5, 2 * (canvas.width / 700));
    const ordered = [...masks].sort((a, b) => Number(highlight?.has(a.id) ?? false) - Number(highlight?.has(b.id) ?? false));

    let raf = 0;
    const draw = (final = false) => {
      const p = still || final ? 1 : Math.min(1, (performance.now() - revealStart.current!.t) / REVEAL_MS);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const m of ordered) {
        if (!visible.has(m.class)) continue;
        const path = paths.get(m.id);
        if (!path) continue;
        const k = Math.max(0, Math.min(1, (p - (order.get(m.id) ?? 0) * 0.7) / 0.3));
        if (k <= 0) continue;
        const color = CLASS_COLORS[m.class] ?? "#888";
        const on = highlight?.has(m.id);
        const dim = anyHighlight && !on;
        ctx.globalAlpha = k;
        ctx.fillStyle = hexToRgba(color, dim ? 0.1 : on ? 0.5 : 0.3);
        ctx.fill(path, "evenodd");
        if (on || k < 1) {
          // a bright rim while each mask lands, and around the selected ones
          ctx.lineWidth = lw * (on ? 2.4 : 1 + 2 * (1 - k));
          ctx.strokeStyle = `rgba(255,255,255,${on ? 0.95 : 0.9 * (1 - k)})`;
          ctx.stroke(path);
        }
        ctx.lineWidth = on ? lw * 1.3 : lw;
        ctx.strokeStyle = hexToRgba(color, dim ? 0.3 : 1);
        ctx.stroke(path);
      }
      ctx.globalAlpha = 1;
      if (p < 1) raf = requestAnimationFrame(() => draw());
    };
    draw();
    // animation frames can be paused (background tab, some WebViews): never leave the masks half drawn
    const left = still ? 0 : REVEAL_MS - (performance.now() - revealStart.current.t);
    const finish = left > 0 ? setTimeout(() => {
      cancelAnimationFrame(raf);
      draw(true);
    }, left + 80) : undefined;
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(finish);
    };
  }, [masks, paths, visible, highlight, order, reveal]);

  function onClick(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!onSelect) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((e.clientY - rect.top) / rect.height) * canvas.height;
    const hits = masks.filter((m) => visible.has(m.class) && ctx.isPointInPath(paths.get(m.id)!, x, y, "evenodd"));
    hits.sort((a, b) => a.area_px - b.area_px); // smallest (most specific) first
    onSelect(hits[0] ?? null);
  }

  return (
    <div
      className={`relative w-full overflow-hidden bg-[#e9e4da] ${rounded ? "rounded-[22px]" : ""} ${fill ? "h-full" : ""}`}
      style={fill ? undefined : { aspectRatio: `${width} / ${height}` }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={imageUrl} alt="Plot photo" className="absolute inset-0 h-full w-full object-cover" draggable={false} />
      <canvas
        ref={canvasRef}
        width={Math.round(width * scale)}
        height={Math.round(height * scale)}
        onClick={onClick}
        className={`absolute inset-0 h-full w-full ${onSelect ? "cursor-crosshair" : ""}`}
      />
    </div>
  );
}

const LAYER_LABELS: Record<string, string> = { crop: "Crop", weed: "Weeds", lesion: "Leaf spots", scale: "A4 sheet" };

export function LayerToggles({ counts, visible, onToggle }: { counts: Record<string, number>; visible: Set<string>; onToggle: (cls: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(LAYER_LABELS)
        .filter(([cls]) => counts[cls] !== undefined)
        .map(([cls, label]) => {
          const on = visible.has(cls);
          const color = CLASS_COLORS[cls];
          return (
            <button
              key={cls}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(cls)}
              className="inline-flex h-8 items-center gap-2 rounded-full px-3 text-[13px] font-semibold transition"
              style={on ? { background: `${color}1f`, color } : { background: "#ece8df", color: "#7f8079" }}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: on ? color : "transparent", boxShadow: `inset 0 0 0 2px ${color}` }} />
              {label}
              <span className="tabular opacity-80">{counts[cls]}</span>
            </button>
          );
        })}
    </div>
  );
}
