"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, EXPERIENCE, Experience, fmtDate, isNativeApp } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { forgetWelcome, PLOTS_CHANGED } from "@/components/AppShell";
import { ServerSettings } from "@/components/ServerSettings";
import { IconBook, IconCamera, IconCheck, IconChevronRight, IconLogout, IconNote, IconSparkle, IconSprout, IconUser, IconVideo } from "@/components/icons";
import { Avatar, Button, Card, ErrorBox, Field, inputClass, LinkButton, PageHead, SectionTitle, Skeleton, Spinner } from "@/components/ui";

/** Settings: your account (or sign in), the app's server (Android app), and about ElderLeaf. */
export function SettingsView() {
  const { me, status } = useAuth();
  const [native, setNative] = useState(false);
  useEffect(() => setNative(isNativeApp()), []);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHead title="Settings" />
      {status === "loading" && <Skeleton className="h-56" />}
      {status === "guest" && <Guest />}
      {status === "signed-in" && me && <SignedIn />}

      {native && (
        <section className="mt-10">
          <SectionTitle>App</SectionTitle>
          <ServerSettings />
        </section>
      )}

      <section className="mt-10">
        <SectionTitle>About</SectionTitle>
        <div className="divide-y divide-line overflow-hidden rounded-[22px] bg-card shadow-[var(--shadow-card)]">
          <AboutRow href="/guide" icon={<IconBook size={19} />} title="Growing guide" text="How to take good photos and what your numbers mean" />
          <AboutRow href="/method" icon={<IconSparkle size={19} />} title="How ElderLeaf measures" text="SAM 3.1 masks, Muse Spark Open, the validator, accuracy" />
        </div>
        <p className="mt-3 px-1 text-xs leading-relaxed text-muted">
          ElderLeaf 1.0 · built for the Meta Global AI Developer Hackathon. It never diagnoses diseases or recommends chemicals.
        </p>
      </section>

      {status === "signed-in" && <SignOut />}
    </div>
  );
}

function AboutRow({ href, icon, title, text }: { href: string; icon: React.ReactNode; title: string; text: string }) {
  return (
    <Link href={href} className="flex items-center gap-3 p-4 transition hover:bg-well">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-semibold">{title}</span>
        <span className="block text-xs text-muted">{text}</span>
      </span>
      <IconChevronRight size={16} className="text-muted" />
    </Link>
  );
}

function SignOut() {
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);
  async function signOut() {
    setLeaving(true);
    await api.logOut();
    forgetWelcome(); // back to the sign-in screen, where "Skip" still lets you continue as a guest
    window.dispatchEvent(new Event(PLOTS_CHANGED));
    router.replace("/login?welcome=1&mode=signin");
  }
  return (
    <Button variant="secondary" size="lg" onClick={signOut} disabled={leaving} className="mt-8 w-full !text-bad sm:w-auto">
      {leaving ? <Spinner /> : <IconLogout size={17} />} Sign out
    </Button>
  );
}

// ------------------------------------------------------------------ guest

function Guest() {
  return (
    <section className="forest-panel relative -mx-4 overflow-hidden px-6 py-8 sm:mx-0 sm:rounded-[32px] sm:px-8">
      <div className="leaf-veins pointer-events-none absolute inset-0" />
      <div className="relative">
        <span className="grid h-16 w-16 place-items-center rounded-full bg-white/10 text-[#f6efe2] ring-1 ring-white/15">
          <IconUser size={30} />
        </span>
        <h2 className="font-display mt-4 text-[30px] font-semibold leading-tight">You are a guest</h2>
        <p className="mt-2 max-w-md text-[15px] leading-relaxed text-[#f6efe2]/80">
          Your plots are saved on this device only. Create an account to keep them safe and open them on any phone or laptop.
        </p>
        <div className="mt-6 flex flex-wrap gap-2.5">
          <LinkButton href="/login?mode=signup" variant="gold" size="lg">
            Create account
          </LinkButton>
          <LinkButton href="/login" variant="glass" size="lg">
            Sign in
          </LinkButton>
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ signed in

function SignedIn() {
  const { me } = useAuth();
  if (!me) return null;
  const level = EXPERIENCE.find((x) => x.id === me.experience);
  const since = new Date(me.created_at).toLocaleDateString("en-GB", { month: "long", year: "numeric" });

  const s = me.stats;
  return (
    <>
      <section className="forest-panel relative -mx-4 overflow-hidden px-6 py-8 sm:mx-0 sm:rounded-[32px] sm:px-8">
        <div className="leaf-veins pointer-events-none absolute inset-0" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
          <Avatar name={me.name} size={84} className="ring-4 ring-white/10" />
          <div className="min-w-0">
            <h2 className="font-display truncate text-[30px] font-semibold leading-tight">{me.name}</h2>
            <p className="truncate text-sm text-[#f6efe2]/70">{me.email}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {me.garden && <span className="glass rounded-full px-3 py-1 text-xs font-semibold">{me.garden}</span>}
              {level && <span className="rounded-full bg-gold px-3 py-1 text-xs font-bold text-forest">{level.label}</span>}
              <span className="glass rounded-full px-3 py-1 text-xs font-semibold">Since {since}</span>
            </div>
          </div>
        </div>
      </section>

      <div className="stagger mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat icon={<IconSprout size={18} />} color="#1f9d55" value={s.plants_counted} label="plants counted" />
        <Stat icon={<IconCamera size={18} />} color="#0891b2" value={s.photos} label={s.photos === 1 ? "photo analysed" : "photos analysed"} />
        <Stat icon={<IconVideo size={18} />} color="#7c4dcc" value={s.videos} label={s.videos === 1 ? "row video" : "row videos"} />
        <Stat icon={<IconNote size={18} />} color="#e8590c" value={s.notes} label={s.notes === 1 ? "note" : "notes"} />
      </div>
      <p className="mt-2 px-1 text-xs text-muted">
        {s.plots} {s.plots === 1 ? "plot" : "plots"}
        {s.first_measured ? ` · measuring since ${fmtDate(s.first_measured)}` : ""}
      </p>

      <EditProfile />
    </>
  );
}

function Stat({ icon, color, value, label }: { icon: React.ReactNode; color: string; value: number; label: string }) {
  return (
    <div className="rounded-[22px] bg-card p-4 shadow-[var(--shadow-card)]">
      <span className="grid h-9 w-9 place-items-center rounded-full" style={{ background: `${color}1a`, color }}>
        {icon}
      </span>
      <div className="tabular mt-3 text-[28px] font-bold leading-none">{value}</div>
      <div className="mt-1 text-xs text-muted">{label}</div>
    </div>
  );
}

function EditProfile() {
  const { me, refresh } = useAuth();
  const [experience, setExperience] = useState<Experience>(me?.experience ?? "just_started");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!me) return null;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateMe({ name: String(f.get("name") ?? ""), garden: String(f.get("garden") ?? "") || null, experience });
      await refresh();
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-10">
      <SectionTitle>Edit profile</SectionTitle>
      <Card>
        <form onSubmit={submit} className="space-y-4" onChange={() => setSaved(false)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name">
              <input name="name" required maxLength={80} defaultValue={me.name} className={inputClass} />
            </Field>
            <Field label="Garden or community">
              <input name="garden" maxLength={120} defaultValue={me.garden ?? ""} placeholder="METU Bostan" className={inputClass} />
            </Field>
          </div>
          <div>
            <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">Growing experience</span>
            <div className="flex flex-wrap gap-2">
              {EXPERIENCE.map((x) => (
                <button
                  key={x.id}
                  type="button"
                  onClick={() => {
                    setExperience(x.id);
                    setSaved(false);
                  }}
                  aria-pressed={experience === x.id}
                  className={`h-9 rounded-full px-4 text-sm font-semibold transition ${experience === x.id ? "bg-brand text-white shadow-sm" : "bg-well text-ink-2 hover:bg-[#ebe7de]"}`}
                >
                  {x.label}
                </button>
              ))}
            </div>
          </div>
          {error && <ErrorBox message={error} />}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy}>
              {busy && <Spinner />} Save
            </Button>
            {saved && (
              <span className="fade-in flex items-center gap-1 text-sm font-semibold text-good">
                <IconCheck size={15} /> Saved
              </span>
            )}
          </div>
        </form>
      </Card>
    </section>
  );
}
