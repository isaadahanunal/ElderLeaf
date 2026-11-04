import { IconCamera, IconCheck, IconCover, IconDroplet, IconEye, IconSparkle, IconSprout, IconSteps, IconVideo } from "@/components/icons";

export const metadata = { title: "How ElderLeaf measures · ElderLeaf" };

const STEPS = [
  { tool: "check_image_quality", title: "Check the photo", text: "Sharpness and light. A poor photo is flagged.", Icon: IconCamera, color: "#7f8079" },
  { tool: "propose_prompts", title: "Decide what to look for", text: "Muse Spark Open looks at the photo and picks SAM phrases, e.g. “lettuce seedling”.", Icon: IconSparkle, color: "#0e7490" },
  { tool: "run_sam", title: "Draw every plant", text: "SAM 3.1 returns a mask per plant and weed, plus the A4 sheet for scale.", Icon: IconEye, color: "#1f9d55" },
  { tool: "compute_metrics", title: "Measure in code", text: "Count, crop cover, weed share, plant size. No language model touches a number.", Icon: IconCover, color: "#0891b2" },
  { tool: "lookup_crop_info", title: "Is this normal?", text: "FAO-56 growth stage for the plant's age and the cover usually seen then.", Icon: IconSprout, color: "#1f9d55" },
  { tool: "get_weather", title: "Water need", text: "Today's ET0 for the plot × crop coefficient, scaled by the measured cover.", Icon: IconDroplet, color: "#2563eb" },
  { tool: "write_summary", title: "Explain it simply", text: "Muse Spark Open writes two or three plain sentences and one thing to do this week.", Icon: IconSparkle, color: "#0e7490" },
  { tool: "validate", title: "Check every word", text: "Each number must match a measurement. No chemicals, doses or diagnoses. Fail → retry.", Icon: IconCheck, color: "#c2185b" },
];

const EVAL = [
  { name: "“crop plant”", count: 8.4, cover: 9.6, note: "finds nothing" },
  { name: "“sugar beet plant”", count: 3.9, cover: 0.8 },
  { name: "“plant”", count: 2.7, cover: 1.1 },
  { name: "Muse Spark Open agent", count: 3.8, cover: 1.1 },
];

export default function MethodPage() {
  const maxCount = Math.max(...EVAL.map((e) => e.count));
  const maxCover = Math.max(...EVAL.map((e) => e.cover));
  return (
    <div>
      <div className="forest-panel relative -mx-4 overflow-hidden px-6 py-10 sm:mx-0 sm:rounded-[32px] sm:px-10">
        <div className="leaf-veins pointer-events-none absolute inset-0" />
        {/* an old hand holding a seedling: a band on top on phones, behind the text on the right on wider screens */}
        <div aria-hidden="true" className="method-band relative -mx-6 -mb-2 -mt-10 sm:hidden" />
        <div aria-hidden="true" className="method-art pointer-events-none absolute inset-0 hidden sm:block" />
        <div className="relative max-w-xl sm:max-w-md lg:max-w-[30rem]">
          <div className="text-sm font-semibold text-white/70">Under the hood</div>
          <h1 className="font-display mt-2 text-[34px] font-semibold leading-tight sm:text-[44px]">A mask behind every number</h1>
          <p className="mt-3 text-[15px] leading-relaxed text-white/85">
            SAM 3.1 draws each plant. Code does the math. Muse Spark Open only chooses what to look for and explains the result, and a validator checks it before you see it.
          </p>
        </div>
        <div className="relative mt-6 flex flex-wrap gap-2">
          {["SAM 3.1", "Muse Spark Open", "FAO-56", "Open-Meteo"].map((t) => (
            <span key={t} className="rounded-full bg-gold/25 px-3 py-1 text-xs font-semibold text-[#f9ecdb] backdrop-blur">
              {t}
            </span>
          ))}
        </div>
      </div>

      <h2 className="font-display mb-3 mt-10 text-[21px] font-semibold">One photo, eight steps</h2>
      <div className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {STEPS.map((s, i) => (
          <div key={s.tool} className="rounded-[22px] bg-card p-5 shadow-[var(--shadow-card)]">
            <div className="flex items-center justify-between">
              <span className="grid h-11 w-11 place-items-center rounded-2xl" style={{ background: `${s.color}1a`, color: s.color }}>
                <s.Icon size={22} />
              </span>
              <span className="text-sm font-bold text-muted">{i + 1}</span>
            </div>
            <div className="mt-4 font-bold">{s.title}</div>
            <p className="mt-1 text-[13px] leading-snug text-muted">{s.text}</p>
            <code className="mt-3 inline-block rounded-full bg-well px-2.5 py-1 font-mono text-[11px] text-ink-2">{s.tool}</code>
          </div>
        ))}
      </div>

      <div className="mt-10 grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-[#1f9d551a] text-[#1f9d55]">
              <IconVideo size={22} />
            </span>
            <div className="font-bold">Counting a whole row</div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-2 text-[13px] font-semibold">
            {["Walk 15 s", "SAM on 2 frames/s", "Follow camera motion", "Match plants by overlap", "Count each id once"].map((t, i, a) => (
              <span key={t} className="flex items-center gap-2">
                <span className="rounded-full bg-well px-3 py-1.5">{t}</span>
                {i < a.length - 1 && <span className="text-muted">→</span>}
              </span>
            ))}
          </div>
          <p className="mt-4 text-[13px] text-muted">On a test walk past 12 plants, never all in view at once, it counts all 12, each once.</p>
        </div>

        <div className="rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-[#0891b21a] text-[#0891b2]">
              <IconSteps size={22} />
            </span>
            <div>
              <div className="font-bold">How accurate is it?</div>
              <div className="text-xs text-muted">PhenoBench, 772 hand-labelled images · lower is better</div>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {EVAL.map((e) => (
              <div key={e.name}>
                <div className="flex justify-between text-[13px]">
                  <span className="font-semibold">{e.name}</span>
                  <span className="tabular text-muted">
                    {e.count} plants off · {e.cover} pts cover{e.note ? ` (${e.note})` : ""}
                  </span>
                </div>
                <div className="mt-1.5 grid grid-cols-2 gap-1.5">
                  <div className="h-2 rounded-full bg-[#efebe3]">
                    <div className="h-2 rounded-full bg-[#1f9d55]" style={{ width: `${(e.count / maxCount) * 100}%` }} />
                  </div>
                  <div className="h-2 rounded-full bg-[#efebe3]">
                    <div className="h-2 rounded-full bg-[#0891b2]" style={{ width: `${(e.cover / maxCover) * 100}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-4 text-xs text-muted">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-[#1f9d55]" /> count error per image
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-4 rounded-full bg-[#0891b2]" /> crop cover error
            </span>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl bg-[#fdebf1] p-6 text-[#7a1238]">
        <div className="font-bold">What ElderLeaf will not do</div>
        <p className="mt-1 text-sm">No disease diagnoses, no pesticide names, no doses. Beginners may trust an app blindly, so unclear signs get an “ask an agronomist” flag instead.</p>
      </div>
    </div>
  );
}
