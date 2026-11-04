"use client";

import Link from "next/link";
import { ReactNode, useEffect, useRef, useState } from "react";
import { initials } from "@/lib/auth";
import {
  IconAlert,
  IconArrowDown,
  IconArrowUp,
  IconCheck,
  IconChevronRight,
  IconCover,
  IconDroplet,
  IconGrass,
  IconHeart,
  IconInfo,
  IconRuler,
  IconSprout,
  IconSpots,
} from "./icons";

// ------------------------------------------------------------------ metric identity (one color per metric)

export const METRIC = {
  plants: { label: "Plants", color: "var(--plants)", hex: "#1f9d55", Icon: IconSprout },
  cover: { label: "Crop cover", color: "var(--cover)", hex: "#0891b2", Icon: IconCover },
  weeds: { label: "Weeds", color: "var(--weeds)", hex: "#e8590c", Icon: IconGrass },
  spots: { label: "Leaf spots", color: "var(--spots)", hex: "#7c4dcc", Icon: IconSpots },
  size: { label: "Plant size", color: "var(--plants)", hex: "#1f9d55", Icon: IconRuler },
  water: { label: "Water", color: "var(--water)", hex: "#2563eb", Icon: IconDroplet },
  health: { label: "Health", color: "var(--health)", hex: "#c2185b", Icon: IconHeart },
} as const;
export type MetricKey = keyof typeof METRIC;

export function MetricIcon({ m, size = 30 }: { m: MetricKey; size?: number }) {
  const { Icon, hex } = METRIC[m];
  return (
    <span className="grid shrink-0 place-items-center rounded-full" style={{ width: size, height: size, background: `${hex}1a`, color: hex }}>
      <Icon size={Math.round(size * 0.55)} />
    </span>
  );
}

// ------------------------------------------------------------------ layout

export function PageHead({ title, chips, actions }: { title: ReactNode; chips?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        <h1 className="font-display line-clamp-2 break-words text-[30px] font-semibold leading-[1.1] sm:text-[34px]">{title}</h1>
        {chips && <div className="mt-2 flex flex-wrap gap-1.5">{chips}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="mb-3 inline-flex items-center gap-1 text-sm font-medium text-muted hover:text-ink">
      <IconChevronRight size={14} className="rotate-180" />
      {label}
    </Link>
  );
}

export function Card({ children, className = "", onClick }: { children: ReactNode; className?: string; onClick?: () => void }) {
  return (
    <div onClick={onClick} className={`rounded-[22px] bg-card p-5 shadow-[var(--shadow-card)] ${onClick ? "cursor-pointer transition hover:shadow-md" : ""} ${className}`}>
      {children}
    </div>
  );
}

export function CardHead({ m, title, right, icon }: { m?: MetricKey; title: ReactNode; right?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      {m ? <MetricIcon m={m} /> : icon}
      <span className="min-w-0 flex-1 truncate text-[15px] font-semibold text-ink-2">{title}</span>
      {right}
    </div>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 mt-2 flex items-center justify-between gap-3">
      <h2 className="font-display text-[21px] font-semibold">{children}</h2>
      {right}
    </div>
  );
}

// ------------------------------------------------------------------ controls

const btn = "inline-flex items-center justify-center gap-2 rounded-full font-semibold transition disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-4";
const btnVariant = {
  primary: "bg-brand text-white hover:bg-forest focus-visible:ring-brand/20",
  secondary: "bg-[#ebe7de] text-ink hover:bg-[#e2ddd2] focus-visible:ring-black/10",
  gold: "bg-gold text-forest shadow-lg hover:brightness-105 focus-visible:ring-gold/30",
  glass: "glass text-[#f6efe2] hover:bg-white/15 focus-visible:ring-white/20",
  white: "bg-card text-ink shadow-[var(--shadow-card)] hover:bg-well focus-visible:ring-black/10",
  ghost: "text-ink-2 hover:bg-black/5 focus-visible:ring-black/10",
};
const btnSize = { sm: "h-8 px-3.5 text-[13px]", md: "h-10 px-4.5 text-sm", lg: "h-12 px-6 text-[15px]" };
type BtnStyle = { variant?: keyof typeof btnVariant; size?: keyof typeof btnSize; className?: string };

export function Button({
  children,
  onClick,
  type = "button",
  variant = "primary",
  size = "md",
  disabled,
  className = "",
}: BtnStyle & { children: ReactNode; onClick?: () => void; type?: "button" | "submit"; disabled?: boolean }) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${btn} ${btnVariant[variant]} ${btnSize[size]} ${className}`}>
      {children}
    </button>
  );
}

export function LinkButton({ href, children, variant = "primary", size = "md", className = "", external }: BtnStyle & { href: string; children: ReactNode; external?: boolean }) {
  const cls = `${btn} ${btnVariant[variant]} ${btnSize[size]} ${className}`;
  return external ? (
    <a href={href} className={cls}>
      {children}
    </a>
  ) : (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}

export function Segmented({ options, value, onChange }: { options: { id: string; label: ReactNode }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div className="inline-flex max-w-full overflow-x-auto rounded-full bg-[#ebe7de] p-1" role="tablist">
      {options.map((o) => (
        <button
          key={o.id}
          role="tab"
          aria-selected={value === o.id}
          onClick={() => onChange(o.id)}
          className={`flex h-9 shrink-0 items-center gap-1.5 rounded-full px-4 text-[13px] font-semibold transition ${value === o.id ? "bg-card text-ink shadow-sm" : "text-muted hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children, className = "" }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "h-11 w-full rounded-xl border border-transparent bg-well px-3.5 text-[15px] text-ink outline-none transition placeholder:text-muted focus:border-brand/40 focus:bg-card focus:ring-4 focus:ring-brand/10";

/** (i) button that opens a short explanation. Keeps the screen free of long text. */
export function InfoTip({ children, label = "How it's computed" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(!open);
        }}
        className={`grid h-6 w-6 place-items-center rounded-full transition ${open ? "bg-ink text-white" : "text-muted hover:bg-black/5 hover:text-ink"}`}
      >
        <IconInfo size={15} />
      </button>
      {open && (
        <span className="fade-in absolute right-0 top-8 z-40 w-72 rounded-xl bg-ink p-3 text-left text-[13px] font-normal leading-snug text-white shadow-xl">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-white/60">{label}</span>
          {children}
        </span>
      )}
    </span>
  );
}

// ------------------------------------------------------------------ status

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "dark" | "brand" }) {
  const tones = {
    neutral: "bg-[#ece8df] text-ink-2",
    good: "bg-good-soft text-good",
    warn: "bg-warn-soft text-warn",
    dark: "bg-ink text-white",
    brand: "bg-brand-soft text-brand",
  };
  return <span className={`inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function StatusChip({ status, children }: { status: "typical" | "attention" | "info"; children?: ReactNode }) {
  if (status === "attention")
    return (
      <Chip tone="warn">
        <IconAlert size={12} />
        {children ?? "Needs a look"}
      </Chip>
    );
  if (status === "typical")
    return (
      <Chip tone="good">
        <IconCheck size={12} />
        {children ?? "Normal"}
      </Chip>
    );
  return <Chip>{children ?? "Info"}</Chip>;
}

export function Delta({ value, unit = "", invert = false }: { value: number | null | undefined; unit?: string; invert?: boolean }) {
  if (value === null || value === undefined) return null;
  if (value === 0) return <span className="tabular text-[13px] font-semibold text-muted">±0</span>;
  const up = value > 0;
  const good = invert ? !up : up;
  const abs = Math.abs(value);
  return (
    <span className={`tabular inline-flex items-center gap-0.5 text-[13px] font-semibold ${good ? "text-good" : "text-bad"}`}>
      {up ? <IconArrowUp size={13} strokeWidth={2.4} /> : <IconArrowDown size={13} strokeWidth={2.4} />}
      {Number.isInteger(abs) ? abs : abs.toFixed(1)}
      {unit}
    </span>
  );
}

export function BigNumber({ value, unit }: { value: ReactNode; unit?: string }) {
  return (
    <span className="tabular text-[36px] font-bold leading-none tracking-tight">
      {value}
      {unit && <span className="ml-0.5 text-lg font-semibold text-muted">{unit}</span>}
    </span>
  );
}

// ------------------------------------------------------------------ figures

/** Fitness-style ring. `band` draws the typical range faintly on the track; `tick` marks a threshold. */
export function Ring({
  value,
  color,
  band,
  tick,
  size = 96,
  stroke = 11,
  children,
}: {
  value: number | null;
  color: string;
  band?: [number, number];
  tick?: number;
  size?: number;
  stroke?: number;
  children?: ReactNode;
}) {
  const r = 50 - stroke / 2 - 1;
  const c = 2 * Math.PI * r;
  const arc = (from: number, to: number) => {
    const a = Math.max(0, Math.min(100, from));
    const b = Math.max(0, Math.min(100, to));
    return { strokeDasharray: `${((b - a) / 100) * c} ${c}`, strokeDashoffset: -(a / 100) * c };
  };
  const v = value === null ? 0 : Math.max(0, Math.min(100, value));
  const tickAngle = tick !== undefined ? (tick / 100) * 2 * Math.PI - Math.PI / 2 : 0;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" width={size} height={size} className="-rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#efebe3" strokeWidth={stroke} />
        {band && <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeOpacity={0.22} strokeWidth={stroke} {...arc(band[0], band[1])} />}
        {v > 0 && (
          <circle
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            className="ring-value"
            style={{ ["--ring-full" as string]: `${c}` }}
            strokeDasharray={`${(v / 100) * c} ${c}`}
          />
        )}
      </svg>
      {tick !== undefined && (
        <span
          className="absolute h-[3px] w-[13px] rounded-full bg-ink/70"
          style={{
            left: `${50 + Math.cos(tickAngle) * (r / 100) * 100}%`,
            top: `${50 + Math.sin(tickAngle) * (r / 100) * 100}%`,
            transform: `translate(-50%, -50%) rotate(${(tick / 100) * 360 + 90}deg)`,
          }}
        />
      )}
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}

/** Tiny column chart for a card: one bar per measurement, the latest in full color. */
export function MiniBars({ values, color, height = 44 }: { values: (number | null)[]; color: string; height?: number }) {
  const vals = values.filter((v): v is number => v !== null).slice(-8);
  if (vals.length === 0) return null;
  const max = Math.max(...vals, 1);
  return (
    <div className="flex items-end gap-1.5" style={{ height }} aria-hidden="true">
      {vals.map((v, i) => (
        <span
          key={i}
          className="w-3 rounded-t-[4px]"
          style={{ height: `${Math.max(6, (v / max) * 100)}%`, background: color, opacity: i === vals.length - 1 ? 1 : 0.32 }}
        />
      ))}
    </div>
  );
}

/** Initials on the brand gold, for the signed-in grower. */
export function Avatar({ name, size = 40, className = "" }: { name?: string | null; size?: number; className?: string }) {
  return (
    <span
      className={`grid shrink-0 select-none place-items-center rounded-full bg-gradient-to-br from-[#d8b87e] to-[#a8834a] font-bold text-forest shadow-sm ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}

/** A number that climbs from 0 when it first appears (the result "moment"). */
export function CountUp({ value, duration = 1400, decimals = 0 }: { value: number; duration?: number; decimals?: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const tick = () => {
      const p = Math.min(1, (performance.now() - t0) / duration);
      setShown(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const end = setTimeout(() => {
      cancelAnimationFrame(raf);
      setShown(value); // never stop short if animation frames are paused
    }, duration + 80);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(end);
    };
  }, [value, duration]);
  return <>{decimals ? shown.toFixed(decimals) : Math.round(shown)}</>;
}

// ------------------------------------------------------------------ misc

export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl bg-[#fde8e8] px-5 py-4 text-sm text-[#8a1c1c]">
      <p>{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="shrink-0 font-semibold underline underline-offset-2">
          Try again
        </button>
      )}
    </div>
  );
}

export function Notice({ tone = "warn", children }: { tone?: "warn" | "info"; children: ReactNode }) {
  return (
    <div className={`flex items-start gap-3 rounded-2xl px-4 py-3 text-sm ${tone === "warn" ? "bg-warn-soft text-warn" : "bg-[#e8f0fe] text-[#1e40af]"}`}>
      <span className="mt-0.5 shrink-0">{tone === "warn" ? <IconAlert size={16} /> : <IconInfo size={16} />}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-[22px] bg-[#ebe7de] ${className}`} />;
}

export function SegmenterNotice({ name }: { name: string | undefined }) {
  if (!name || name === "SAM 3.1") return null;
  return (
    <Notice>
      Masks drawn by the <b>{name}</b>, a development fallback. Real analyses use SAM 3.1.
    </Notice>
  );
}
