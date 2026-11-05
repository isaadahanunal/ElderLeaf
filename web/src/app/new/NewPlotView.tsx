"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, today } from "@/lib/api";
import { PLOTS_CHANGED } from "@/lib/events";
import { IconPin } from "@/components/icons";
import { BackLink, Button, Card, ErrorBox, Field, inputClass, PageHead, Spinner } from "@/components/ui";

const CROPS = [
  ["lettuce", "Lettuce"],
  ["spinach", "Spinach"],
  ["cabbage", "Cabbage"],
  ["onion", "Onion"],
  ["garlic", "Garlic"],
  ["broad_bean", "Broad bean"],
  ["tomato", "Tomato"],
  ["pepper", "Pepper"],
  ["wheat", "Wheat"],
  ["sugar_beet", "Sugar beet"],
  ["other", "Other"],
];

export function NewPlotView() {
  const router = useRouter();
  return (
    <div className="max-w-2xl">
      <BackLink href="/" label="All plots" />
      <PageHead title="New plot" />
      <NewPlotForm onCancel={() => router.back()} />
    </div>
  );
}

/** The new-plot form. `bare` drops the cards, for use inside a sheet. After saving it opens the camera screen. */
export function NewPlotForm({ onCancel, onDone, bare = false }: { onCancel: () => void; onDone?: () => void; bare?: boolean }) {
  const router = useRouter();
  const Section = bare ? "div" : Card;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crop, setCrop] = useState("lettuce");
  // more than one crop in the same photo: the agent then lists every kind of plant it sees (scan mode)
  const [mixed, setMixed] = useState(false);
  const [others, setOthers] = useState<string[]>([]);
  const [loc, setLoc] = useState<{ lat: number; lon: number } | null>(null);
  const [locState, setLocState] = useState<"asking" | "denied" | "done">("asking");

  useEffect(() => {
    if (!("geolocation" in navigator)) return setLocState("denied");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLoc({ lat: +p.coords.latitude.toFixed(4), lon: +p.coords.longitude.toFixed(4) });
        setLocState("done");
      },
      () => setLocState("denied"),
      { timeout: 8000, maximumAge: 600000 },
    );
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const num = (k: string) => (f.get(k) ? Number(f.get(k)) : null);
    if (mixed && others.length === 0) {
      setError("Pick the other crops in this bed, or choose One crop.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const plot = await api.createPlot({
        name: String(f.get("name")),
        crop,
        mixed,
        other_crops: mixed ? others : [],
        planted_on: f.get("planted_on") || null,
        area_m2: num("area_m2"),
        row_spacing_cm: num("row_spacing_cm"),
        plant_spacing_cm: num("plant_spacing_cm"),
        lat: num("lat") ?? loc?.lat ?? null,
        lon: num("lon") ?? loc?.lon ?? null,
      });
      window.dispatchEvent(new Event(PLOTS_CHANGED));
      onDone?.();
      router.push(`/analyze?plot=${plot.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
      <form onSubmit={submit} className="space-y-4">
        <Section className="space-y-4">
          <Field label="Name">
            <input name="name" required maxLength={120} placeholder="Bed 3 by the fence" className={inputClass} />
          </Field>
          <div>
            <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">Crop</span>
            <div className="flex flex-wrap gap-2">
              {CROPS.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => {
                    setCrop(id);
                    setOthers((o) => o.filter((x) => x !== id));
                  }}
                  className={`h-9 rounded-full px-4 text-sm font-semibold transition ${crop === id ? "bg-brand text-white shadow-sm" : "bg-well text-ink-2 hover:bg-[#ebe7de]"}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">Crops in the photo</span>
            <div className="flex flex-wrap gap-2">
              {([[false, "One crop"], [true, "More than one"]] as const).map(([value, label]) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => setMixed(value)}
                  className={`h-9 rounded-full px-4 text-sm font-semibold transition ${mixed === value ? "bg-brand text-white shadow-sm" : "bg-well text-ink-2 hover:bg-[#ebe7de]"}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="mt-1 block text-xs text-muted">
              {mixed ? "ElderLeaf lists every kind of plant it sees and counts each crop." : "ElderLeaf picks the best search words for this crop."}
            </span>
          </div>
          {mixed && (
            <div>
              <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">Other crops in the same photo</span>
              <div className="flex flex-wrap gap-2">
                {CROPS.filter(([id]) => id !== crop).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setOthers((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]))}
                    className={`h-9 rounded-full px-4 text-sm font-semibold transition ${others.includes(id) ? "bg-brand text-white shadow-sm" : "bg-well text-ink-2 hover:bg-[#ebe7de]"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <span className="mt-1 block text-xs text-muted">Pick &quot;Other&quot; if you are not sure what it is.</span>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Planted on" hint="To tell if growth is normal for its age.">
              <input name="planted_on" type="date" max={today()} className={inputClass} />
            </Field>
            <Field label="Area (m²)" hint="For the plot's total water need.">
              <input name="area_m2" type="number" min="0.1" step="0.1" inputMode="decimal" placeholder="4" className={inputClass} />
            </Field>
          </div>
        </Section>

        <Section className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Row spacing (cm)">
              <input name="row_spacing_cm" type="number" min="1" inputMode="decimal" placeholder="Optional" className={inputClass} />
            </Field>
            <Field label="Plant spacing (cm)">
              <input name="plant_spacing_cm" type="number" min="1" inputMode="decimal" placeholder="Optional" className={inputClass} />
            </Field>
          </div>
          <div className="flex items-center gap-3 rounded-2xl bg-well px-4 py-3 text-sm">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#2563eb1a] text-water">
              <IconPin size={18} />
            </span>
            <span className="text-ink-2">
              {locState === "asking" && "Finding your location for local weather…"}
              {locState === "done" && loc && `Location saved (${loc.lat}, ${loc.lon}) for local weather.`}
              {locState === "denied" && "Location not shared. Add it below for water estimates."}
            </span>
          </div>
          {locState === "denied" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Latitude">
                <input name="lat" type="number" step="0.0001" min="-90" max="90" placeholder="39.8910" className={inputClass} />
              </Field>
              <Field label="Longitude">
                <input name="lon" type="number" step="0.0001" min="-180" max="180" placeholder="32.7830" className={inputClass} />
              </Field>
            </div>
          )}
        </Section>

        {error && <ErrorBox message={error} />}
        <div className="flex gap-2">
          <Button type="submit" size="lg" disabled={busy}>
            {busy && <Spinner />} Create and take a photo
          </Button>
          <Button variant="secondary" size="lg" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
  );
}
