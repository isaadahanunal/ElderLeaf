"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { openCaptureSheet, openNewPlotSheet } from "@/components/AppShell";
import { IconAlert, IconCamera, IconCheck, IconChevronRight, IconFlag, IconPlus } from "@/components/icons";
import { Button, METRIC, MetricKey, SectionTitle } from "@/components/ui";

// each step is a shortcut: a link (href) or the camera sheet (camera)
const STEPS: { title: string; text: string; icon: ReactNode; cta: string; href?: string; camera?: boolean; newPlot?: boolean }[] = [
  {
    title: "Add your plot",
    text: "Give it a name, pick the crop and the day you planted it. The planting day is how ElderLeaf knows what is normal for your plants' age.",
    icon: <IconPlus size={20} strokeWidth={2.2} />,
    cta: "Add a plot",
    newPlot: true,
  },
  {
    title: "Take one photo from above",
    text: "Stand at the same spot every time (a stake or a stone helps), hold the phone flat about 1–1.5 m over the bed, and put an A4 sheet in the frame to get sizes in cm².",
    icon: <IconCamera size={20} />,
    cta: "Open the camera",
    camera: true,
  },
  {
    title: "Come back every week",
    text: "Each photo goes into the plot's logbook with your notes. Compare two dates side by side to see how much your plants grew.",
    icon: <IconCheck size={20} strokeWidth={2.4} />,
    cta: "See what is due today",
    href: "/today",
  },
];

const NUMBERS: { m: MetricKey; title: string; text: string }[] = [
  { m: "plants", title: "Plants", text: "How many crop plants were found in the photo. Tap a plant on the photo to see its outline." },
  {
    m: "cover",
    title: "Crop cover",
    text: "How much of the ground the leaves cover. It rises as the plants grow; the faint band on the ring shows what is typical for your crop at this age.",
  },
  { m: "weeds", title: "Weeds", text: "The share of all the green that is weeds. Above 25% it is a good week to weed." },
  { m: "size", title: "Plant size", text: "The average leaf area of one plant, in cm² when the A4 sheet is in the photo. Watch it grow from week to week." },
  {
    m: "water",
    title: "Water today",
    text: "Litres your plot needs today: the local weather times what your crop needs at this stage, less while the plants are still small. Rain is counted.",
  },
  {
    m: "health",
    title: "Plant health",
    text: "Possible signs only, like yellowing or spots. ElderLeaf never names a disease, because the same sign can have many causes.",
  },
];

const PHOTO_TIPS = [
  "The same spot and height every time",
  "The whole bed in the frame",
  "Soft light: early morning, evening or a cloudy day",
  "No harsh shadows, your own included",
  "Hold still for a second before you tap",
];

export function GuideView() {
  return (
    <div className="mx-auto max-w-3xl">
      <section className="forest-panel relative -mx-4 overflow-hidden px-6 pb-8 pt-10 sm:mx-0 sm:rounded-[32px] sm:px-10">
        <div className="leaf-veins pointer-events-none absolute inset-0" />
        <div aria-hidden="true" className="method-band relative -mx-6 -mb-2 -mt-10 sm:hidden" />
        <div aria-hidden="true" className="method-art pointer-events-none absolute inset-0 hidden sm:block" />
        <div className="relative sm:max-w-sm">
          <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-gold">Growing guide</div>
          <h1 className="font-display mt-2 text-[34px] font-semibold leading-[1.08] sm:text-[40px]">Grow with an old hand beside you</h1>
          <p className="mt-3 text-[15px] leading-relaxed text-[#f6efe2]/80">One photo a week is enough. Here is how to take it and what the numbers tell you.</p>
        </div>
      </section>

      <section className="mt-10">
        <SectionTitle>Start in three steps</SectionTitle>
        <ol className="stagger space-y-3">
          {STEPS.map((s, i) => {
            const body = (
              <>
                <span className="relative grid h-11 w-11 shrink-0 place-items-center rounded-full bg-brand text-[#f6efe2]">
                  {s.icon}
                  <span className="absolute -right-1 -top-1 grid h-5 w-5 place-items-center rounded-full bg-gold text-[11px] font-bold text-forest">{i + 1}</span>
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[16px] font-semibold">{s.title}</span>
                  <span className="mt-0.5 block text-sm leading-relaxed text-ink-2">{s.text}</span>
                  <span className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand">
                    {s.cta} <IconChevronRight size={14} />
                  </span>
                </span>
              </>
            );
            const cls = "flex w-full gap-4 rounded-[22px] bg-card p-4 text-left shadow-[var(--shadow-card)] transition hover:shadow-md active:scale-[0.99]";
            return (
              <li key={s.title}>
                {s.href ? (
                  <Link href={s.href} className={cls}>
                    {body}
                  </Link>
                ) : (
                  <button type="button" onClick={() => (s.newPlot ? openNewPlotSheet() : openCaptureSheet())} className={cls}>
                    {body}
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      </section>

      <section className="mt-10">
        <SectionTitle>What your numbers mean</SectionTitle>
        <p className="-mt-1 mb-3 text-sm text-ink-2">
          Every number comes with a label, <b className="text-good">Normal</b> or <b className="text-warn">Needs a look</b>, judged for your crop and its age. Tap the{" "}
          <span className="inline-grid h-5 w-5 translate-y-1 place-items-center rounded-full border border-line text-[11px] font-bold text-muted">i</span> on a card to see how it was
          worked out.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {NUMBERS.map((n) => {
            const { hex, Icon } = METRIC[n.m];
            return (
              <div key={n.title} className="rounded-[22px] bg-card p-4 shadow-[var(--shadow-card)]">
                <div className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 place-items-center rounded-full" style={{ background: `${hex}1a`, color: hex }}>
                    <Icon size={17} />
                  </span>
                  <span className="text-[15px] font-semibold">{n.title}</span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{n.text}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="mt-10">
        <div className="rounded-[22px] bg-card p-5 shadow-[var(--shadow-card)]">
          <div className="text-[16px] font-semibold">A good photo</div>
          <ul className="mt-3 space-y-2.5">
            {PHOTO_TIPS.map((t) => (
              <li key={t} className="flex gap-2.5 text-sm text-ink-2">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-good-soft text-good">
                  <IconCheck size={12} strokeWidth={2.8} />
                </span>
                {t}
              </li>
            ))}
          </ul>
          <Button variant="secondary" onClick={() => openCaptureSheet()} className="mt-4">
            <IconCamera size={16} /> Take a photo
          </Button>
        </div>
      </section>

      <section className="mt-3 rounded-[22px] border border-[#f3c7d6] bg-[#fdf1f5] p-5">
        <div className="flex items-center gap-2 text-[16px] font-semibold text-[#8f1d47]">
          <IconFlag size={17} /> When to ask someone
        </div>
        <p className="mt-2 text-sm leading-relaxed text-[#6b2440]">
          If a result says <b>Ask an agronomist</b>, the photo was unclear, many leaves showed spots, or ElderLeaf was not sure. Show the plant to an experienced grower
          or an agronomist. ElderLeaf never names a disease, a chemical or a dose: a beginner might trust a wrong answer.
        </p>
        <p className="mt-3 flex items-center gap-2 text-xs text-[#8f1d47]/80">
          <IconAlert size={13} /> The same goes for any sign you are unsure about, even without the flag.
        </p>
      </section>

      <Link href="/method" className="mt-8 flex items-center gap-3 rounded-[22px] bg-card p-4 shadow-[var(--shadow-card)] transition hover:shadow-md">
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-semibold">Curious how it works under the hood?</span>
          <span className="block text-xs text-muted">How ElderLeaf measures: SAM 3.1 masks, Muse Spark Open, the validator, accuracy</span>
        </span>
        <IconChevronRight size={16} className="text-muted" />
      </Link>
    </div>
  );
}
